"""Streamlit dashboard for the CloudCompass college-project demo."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.express as px

from cloudcompass.analysis import build_decision_memo, rank_bottlenecks
from cloudcompass.config import DEFAULT_PROVIDERS, RISK_PROFILES
from cloudcompass.data import WorkloadConfig, generate_workload, load_trace_csv
from cloudcompass.scenarios import evaluate_scenario, stress_test


st.set_page_config(page_title="CloudCompass", page_icon="CC", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px;}
[data-testid="stMetricValue"] {font-size: 1.8rem;}
.hero {background: linear-gradient(120deg,#0b1220,#162d50); color:#f5f8ff; padding:28px 32px; border-radius:20px; margin-bottom:20px;}
.hero h1 {margin:0 0 8px 0; letter-spacing:-.04em;}
.hero p {margin:0; color:#b8c7e5; font-size:1.05rem;}
.memo {background:#eef6ff; border-left:5px solid #2274d4; padding:16px 18px; border-radius:10px; line-height:1.55;}
.small {color:#6b7280; font-size:.86rem;}
</style>
""", unsafe_allow_html=True)


def _money(value: float) -> str:
    return f"${value:,.2f}"


def main() -> None:
    st.markdown('<div class="hero"><h1>CloudCompass</h1><p>Risk-aware cloud commitment planning for changing workloads</p></div>', unsafe_allow_html=True)
    st.caption("A transparent academic simulator: every recommendation is reproducible, inspectable, and tied to a cost-versus-risk decision.")

    with st.sidebar:
        st.header("Scenario controls")
        hours = st.slider("Workload horizon (hours)", 24, 336, 168, step=24)
        provider_name = st.selectbox("Cloud provider", [p.name for p in DEFAULT_PROVIDERS], index=2)
        risk = st.radio("Risk posture", list(RISK_PROFILES), index=1, format_func=lambda x: f"{x.title()} - {RISK_PROFILES[x]['label']}")
        error = st.select_slider("Forecast error", options=(-50, -25, -10, 0, 10, 25, 50), value=0, format_func=lambda x: f"{x:+d}%")
        cycle_weeks = st.radio("Commitment ladder", (4, 8), horizontal=True)
        offpeak = st.toggle("Enable off-peak shifting", value=True)
        uploaded = st.file_uploader("Optional demand CSV", type=["csv"], help="Use a file with a numeric 'demand' column.")

    provider = next(p for p in DEFAULT_PROVIDERS if p.name == provider_name)
    workload = load_trace_csv(uploaded, hours=hours) if uploaded else generate_workload(WorkloadConfig(hours=hours))
    result = evaluate_scenario(workload, provider, error, risk, cycle_weeks, offpeak)
    stress = stress_test(workload, provider, risk, cycle_weeks, offpeak)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommended commitment", f"{result['forecast_commitment']} units")
    c2.metric("Projected cost", _money(result["actual_cost"]))
    c3.metric("Savings vs on-demand", f"{result['savings_percent']:.1f}%", f"{_money(result['savings'])}")
    c4.metric("Quota used", f"{result['quota_utilization']:.1f}%")

    st.markdown(f'<div class="memo"><b>Decision memo</b><br>{build_decision_memo(result, stress)}</div>', unsafe_allow_html=True)
    st.write("")

    overview, risk_lab, ladder, diagnostics = st.tabs(["Workload view", "Risk lab", "Commitment ladder", "Bottlenecks"])
    with overview:
        chart_data = workload[["timestamp", "demand", "forecast"]].copy()
        chart_data = chart_data.melt("timestamp", var_name="series", value_name="units")
        st.plotly_chart(px.line(chart_data, x="timestamp", y="units", color="series", title="Actual demand vs baseline forecast"), use_container_width=True)
        st.caption("The blue recommendation is intentionally explainable: fixed demand remains in place and flexible work can move into spare committed capacity.")
    with risk_lab:
        risk_chart = px.line(stress, x="error_percent", y="actual_cost", markers=True, title="Forecast error changes the realized weekly cost")
        risk_chart.update_xaxes(title="Forecast error (%)")
        risk_chart.update_yaxes(title="Realized cost ($)")
        st.plotly_chart(risk_chart, use_container_width=True)
        st.dataframe(stress[["error_percent", "forecast_commitment", "actual_cost", "savings_percent", "on_demand_units"]], use_container_width=True, hide_index=True)
    with ladder:
        ladder_frame = pd.DataFrame(result["ladder"])
        st.plotly_chart(px.timeline(ladder_frame, x_start="starts_week", x_end="expires_week", y="block", color="type", text="capacity", title=f"{cycle_weeks}-week staggered commitment plan"), use_container_width=True)
        st.dataframe(ladder_frame, use_container_width=True, hide_index=True)
    with diagnostics:
        for item in rank_bottlenecks(stress):
            icon = "High" if item["severity"] == "high" else "Watch" if item["severity"] == "medium" else "OK"
            st.info(f"**{icon}: {item['name']}** - {item['evidence']}")
        st.dataframe(pd.DataFrame([result["plan"]])[['provider', 'region', 'status', 'commitment', 'solver', 'shadow_price_per_hour', 'quota_shadow_price']], use_container_width=True, hide_index=True)

    st.markdown('<p class="small">CloudCompass is an educational simulator, not a live cloud billing estimator. Replace the synthetic trace with a validated dataset before operational use.</p>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
