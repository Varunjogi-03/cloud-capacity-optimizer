"""Narrative analysis for an explainable college-project demo."""

from __future__ import annotations

import pandas as pd


def rank_bottlenecks(stress: pd.DataFrame) -> list[dict]:
    """Name the constraints that deserve operational attention."""
    if stress.empty:
        return []
    latest = stress.iloc[stress["error_percent"].abs().argmax()]
    bottlenecks = []
    if float(latest["quota_utilization"]) >= 80:
        bottlenecks.append({"name": "Provider quota", "severity": "high",
                            "evidence": f"{latest['quota_utilization']:.1f}% of quota is committed."})
    if int(latest["on_demand_units"]) > 0:
        bottlenecks.append({"name": "On-demand exposure", "severity": "medium",
                            "evidence": f"{int(latest['on_demand_units'])} hourly units spill into on-demand pricing."})
    if float(stress["savings_percent"].max() - stress["savings_percent"].min()) > 10:
        bottlenecks.append({"name": "Forecast sensitivity", "severity": "medium",
                            "evidence": "Savings move materially across the forecast-error band."})
    return bottlenecks or [{"name": "No critical bottleneck", "severity": "low",
                            "evidence": "The tested plan stays inside quota with limited on-demand exposure."}]


def build_decision_memo(result: dict, stress: pd.DataFrame) -> str:
    """Return a short recommendation a student can explain line by line."""
    direction = "saves" if result["savings"] >= 0 else "costs"
    best = stress.loc[stress["actual_cost"].idxmin()]
    worst = stress.loc[stress["actual_cost"].idxmax()]
    bottleneck = rank_bottlenecks(stress)[0]
    return (
        f"CloudCompass recommends {result['forecast_commitment']} committed units in {result['provider']} "
        f"({result['region']}) using the {result['risk']} risk posture. The plan {direction} "
        f"${abs(result['savings']):,.2f} versus pure on-demand for the tested week, while using "
        f"{result['quota_utilization']:.1f}% of provider quota. A {result['cycle_weeks']}-week ladder "
        f"keeps part of the commitment flexible, and off-peak shifting is "
        f"{'enabled' if result['offpeak'] else 'disabled'}. Across the stress test, the cheapest case is "
        f"{int(best['error_percent']):+d}% forecast error and the most expensive is "
        f"{int(worst['error_percent']):+d}%. Primary watch item: {bottleneck['name']} - {bottleneck['evidence']}"
    )
