"""Streamlit dashboard for the CloudCompass college-project demo."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Streamlit Community Cloud may execute this nested entrypoint with the
# ``cloudcompass`` package directory as sys.path[0]. Add the repository root
# explicitly so package imports work both locally and on hosted deployments.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cloudcompass.analysis import build_decision_memo, rank_bottlenecks
from cloudcompass.config import DEFAULT_PROVIDERS, RISK_PROFILES
from cloudcompass.data import (
    WorkloadConfig,
    generate_workload,
    load_shaved_ice_trace,
    load_trace_csv,
    shaved_ice_series,
)
from cloudcompass.scenarios import evaluate_scenario, stress_test


st.set_page_config(page_title="CloudCompass", page_icon="CC", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px;}
[data-testid="stMetricValue"] {font-size: 1.8rem;}
.hero {background: linear-gradient(120deg,#0b1220,#162d50); color:#f5f8ff; padding:28px 32px; border-radius:20px; margin-bottom:20px;}
.hero h1 {margin:0 0 8px 0; letter-spacing:-.04em;}
.hero p {margin:0; color:#b8c7e5; font-size:1.05rem;}
.memo {background:#eef6ff; color:#172033 !important; border-left:5px solid #2274d4; padding:16px 18px; border-radius:10px; line-height:1.55;}
.memo, .memo * {color:#172033 !important;}
.memo b, .memo strong {color:#0b2545 !important;}
.small {color:#6b7280; font-size:.86rem;}
</style>
""", unsafe_allow_html=True)


def _money(value: float) -> str:
    return f"${value:,.2f}"


SHAVED_ICE_PATH = PROJECT_ROOT / "dataset" / "hourly_normalized.csv.gz"


@st.cache_data(show_spinner=False)
def _shaved_ice_options(path: str) -> tuple[list[int], list[str]]:
    return shaved_ice_series(path)


@st.cache_data(show_spinner="Loading the selected Shaved Ice workload...")
def _load_shaved_ice(path: str, region: int, vm_type: str, hours: int, start_hour: int) -> pd.DataFrame:
    return load_shaved_ice_trace(path, region, vm_type, hours, start_hour)


def _ladder_chart(ladder: pd.DataFrame, cycle_weeks: int) -> go.Figure:
    """Render a numeric week-based Gantt chart for commitment blocks.

    Plotly Express timelines interpret numeric values as calendar timestamps;
    these commitments are durations measured in weeks, so use bar bases on a
    numeric x-axis instead.
    """
    frame = ladder.copy()
    frame["duration_weeks"] = frame["expires_week"] - frame["starts_week"]
    colors = {"core commitment": "#3b82f6", "staggered": "#38bdf8"}
    chart = go.Figure()
    for block_type, group in frame.groupby("type", sort=False):
        chart.add_trace(go.Bar(
            name=block_type.title(),
            y=group["block"],
            x=group["duration_weeks"],
            base=group["starts_week"],
            orientation="h",
            marker_color=colors.get(block_type, "#64748b"),
            text=[f"{int(capacity)} units" for capacity in group["capacity"]],
            textposition="inside",
            insidetextanchor="middle",
            customdata=group[["starts_week", "expires_week", "capacity"]],
            hovertemplate=("<b>%{y}</b><br>Capacity: %{customdata[2]} units"
                           "<br>Starts: week %{customdata[0]:g}"
                           "<br>Expires: week %{customdata[1]:g}<extra></extra>"),
        ))
    chart.update_layout(
        title=f"{cycle_weeks}-week staggered commitment plan",
        barmode="overlay",
        height=360,
        xaxis_title="Weeks from commitment start",
        yaxis_title="Commitment block",
        legend_title="Block type",
        margin=dict(l=30, r=30, t=55, b=45),
    )
    chart.update_xaxes(range=[0, cycle_weeks], dtick=1, tickmode="linear", gridcolor="rgba(148,163,184,.25)")
    chart.update_yaxes(categoryorder="array", categoryarray=list(reversed(frame["block"].tolist())))
    return chart


def main() -> None:
    st.markdown('<div class="hero"><h1>CloudCompass</h1><p>Risk-aware cloud commitment planning for changing workloads</p></div>', unsafe_allow_html=True)
    st.caption("A transparent academic simulator: every recommendation is reproducible, inspectable, and tied to a cost-versus-risk decision.")

    with st.sidebar:
        st.header("Scenario controls")
        hours = st.slider("Workload horizon (hours)", 24, 336, 168, step=24)
        source_options = ["Synthetic demo", "Upload demand CSV"]
        if SHAVED_ICE_PATH.exists():
            source_options.insert(0, "Shaved Ice dataset (bundled)")
        source = st.radio("Workload source", source_options, index=0)
        shaved_region = 1
        shaved_vm_type = "A"
        shaved_start_hour = 0
        uploaded = None
        if source == "Shaved Ice dataset (bundled)":
            regions, vm_types = _shaved_ice_options(str(SHAVED_ICE_PATH))
            shaved_region = st.selectbox("Shaved Ice region", regions)
            shaved_vm_type = st.selectbox("Shaved Ice VM type", vm_types)
            shaved_start_hour = st.number_input("Trace start hour", min_value=0, value=0, step=24,
                                                help="Offset into the selected hourly trace; use this to inspect a different period.")
        elif source == "Upload demand CSV":
            uploaded = st.file_uploader("Demand CSV", type=["csv"], help="Use a file with a numeric 'demand' column.")
        provider_name = st.selectbox("Cloud provider", [p.name for p in DEFAULT_PROVIDERS], index=2)
        risk = st.radio("Risk posture", list(RISK_PROFILES), index=1, format_func=lambda x: f"{x.title()} - {RISK_PROFILES[x]['label']}")
        error = st.select_slider("Forecast error", options=(-50, -25, -10, 0, 10, 25, 50), value=0, format_func=lambda x: f"{x:+d}%")
        cycle_weeks = st.radio("Commitment ladder", (4, 8), horizontal=True)
        offpeak = st.toggle("Enable off-peak shifting", value=True)

    if source == "Shaved Ice dataset (bundled)":
        workload = _load_shaved_ice(str(SHAVED_ICE_PATH), shaved_region, shaved_vm_type, hours, int(shaved_start_hour))
        source_label = f"Shaved Ice: region {shaved_region}, VM type {shaved_vm_type}"
    elif source == "Upload demand CSV" and uploaded is not None:
        workload = load_trace_csv(uploaded, hours=hours)
        source_label = "Uploaded CSV"
    else:
        workload = generate_workload(WorkloadConfig(hours=hours))
        source_label = "Reproducible synthetic demo"

    base_provider = next(p for p in DEFAULT_PROVIDERS if p.name == provider_name)
    quota_max = max(base_provider.quota, int(workload[["demand", "forecast"]].max().max()))
    quota_default = min(base_provider.quota, quota_max)
    quota = st.sidebar.slider("Commitment quota", min_value=1, max_value=quota_max, value=quota_default,
                              help="Limits committed capacity. Lower it below the unconstrained recommendation to expose a non-zero quota shadow price.")
    provider = replace(base_provider, quota=quota)
    result = evaluate_scenario(workload, provider, error, risk, cycle_weeks, offpeak)
    stress = stress_test(workload, provider, risk, cycle_weeks, offpeak)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommended commitment", f"{result['forecast_commitment']} units")
    c2.metric("Projected cost", _money(result["actual_cost"]))
    c3.metric("Savings vs on-demand", f"{result['savings_percent']:.1f}%", f"{_money(result['savings'])}")
    c4.metric("Quota used", f"{result['quota_utilization']:.1f}%", f"shadow ${result['quota_shadow_price']:.4f}/hr")

    st.markdown(f'<div class="memo"><b>Decision memo</b><br>{build_decision_memo(result, stress)}</div>', unsafe_allow_html=True)
    st.write("")

    overview, risk_lab, ladder, diagnostics = st.tabs(["Workload view", "Risk lab", "Commitment ladder", "Bottlenecks"])
    with overview:
        chart_data = workload[["timestamp", "demand", "forecast"]].copy()
        chart_data = chart_data.melt("timestamp", var_name="series", value_name="units")
        st.plotly_chart(px.line(chart_data, x="timestamp", y="units", color="series", title="Actual demand vs baseline forecast"), use_container_width=True)
        st.caption(f"Source: {source_label}. Fixed demand remains in place and flexible work can move into spare committed capacity.")
    with risk_lab:
        risk_chart = px.line(stress, x="error_percent", y="actual_cost", markers=True, title="Forecast error changes the realized weekly cost")
        risk_chart.update_xaxes(title="Forecast error (%)")
        risk_chart.update_yaxes(title="Realized cost ($)")
        st.plotly_chart(risk_chart, use_container_width=True)
        st.dataframe(stress[["error_percent", "forecast_commitment", "committed_cost", "actual_cost", "savings_percent", "on_demand_units", "quota_shadow_price"]], use_container_width=True, hide_index=True)
    with ladder:
        ladder_frame = pd.DataFrame(result["ladder"])
        l1, l2 = st.columns(2)
        l1.metric("Committed cost (tested horizon)", _money(result["committed_cost"]))
        l2.metric("Term discount", f"{result['term_discount_percent']:.1f}%")
        st.plotly_chart(_ladder_chart(ladder_frame, cycle_weeks), use_container_width=True)
        st.caption("Each ladder block starts now and expires at a different time. Expired blocks stop contributing committed capacity and cost, so the selected ladder changes the simulated cost and on-demand exposure.")
        st.dataframe(ladder_frame, use_container_width=True, hide_index=True)
    with diagnostics:
        for item in rank_bottlenecks(stress):
            icon = "High" if item["severity"] == "high" else "Watch" if item["severity"] == "medium" else "OK"
            st.info(f"**{icon}: {item['name']}** - {item['evidence']}")
        st.dataframe(pd.DataFrame([result["plan"]])[['provider', 'region', 'status', 'commitment', 'solver', 'shadow_price_per_hour', 'quota_shadow_price']], use_container_width=True, hide_index=True)

    st.markdown('<p class="small">CloudCompass is an educational simulator, not a live cloud billing estimator. Bundled Shaved Ice demand is normalized and provider rates remain illustrative.</p>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
