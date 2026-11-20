"""Forecast stress tests, strategy comparison, and commitment laddering."""

from __future__ import annotations

from dataclasses import asdict
import math

import numpy as np
import pandas as pd

from .config import DEFAULT_PROVIDERS, RISK_PROFILES, Provider
from .data import apply_forecast_error, validate_workload
from .optimizer import OptimizationResult, optimize_capacity
from .scheduler import schedule_offpeak


def make_commitment_ladder(commitment: int, hours: int, cycle_weeks: int, ladder_share: float) -> pd.DataFrame:
    """Create a small staggered schedule that is easy to explain in a viva."""
    if cycle_weeks not in (4, 8):
        raise ValueError("cycle_weeks must be 4 or 8")
    blocks = cycle_weeks
    long_term = int(round(commitment * ladder_share))
    short_term = max(0, commitment - long_term)
    rows = []
    for index in range(blocks):
        rows.append({
            "block": index + 1,
            "starts_week": index * (cycle_weeks // 2),
            "expires_week": (index + 1) * (cycle_weeks // 2),
            "capacity": int(round(short_term / blocks)) if short_term else 0,
            "type": "staggered",
        })
    rows.insert(0, {"block": "core", "starts_week": 0, "expires_week": cycle_weeks,
                    "capacity": long_term, "type": "core commitment"})
    return pd.DataFrame(rows)


def evaluate_scenario(workload: pd.DataFrame, provider: Provider, error_percent: int = 0,
                      risk: str = "balanced", cycle_weeks: int = 4,
                      offpeak: bool = True) -> dict:
    """Evaluate one demand forecast under actual demand and return all evidence."""
    validate_workload(workload)
    if risk not in RISK_PROFILES:
        raise ValueError(f"risk must be one of {sorted(RISK_PROFILES)}")
    forecast = apply_forecast_error(workload, error_percent)
    profile = RISK_PROFILES[risk]
    # The risk budget blends the stressed forecast with a high-demand quantile.
    # The risk budget deliberately changes the planned target: conservative
    # users buy a small buffer, while aggressive users accept more spillover.
    risk_bias = {"aggressive": -0.08, "balanced": 0.0, "conservative": 0.10}[risk]
    target = np.maximum(1, np.rint(forecast * (1 + risk_bias))).astype(int)
    plan: OptimizationResult = optimize_capacity(target, provider)
    scheduled = schedule_offpeak(workload, pd.Series(plan.commitment, index=workload.index)) if offpeak else workload.copy()
    if not offpeak:
        scheduled["scheduled_demand"] = scheduled["demand"]
    evaluated_demand = scheduled["scheduled_demand"].to_numpy() if offpeak else workload["demand"].to_numpy()
    actual_on_demand = np.maximum(evaluated_demand - plan.commitment, 0)
    actual_cost = plan.commitment * len(workload) * provider.committed_rate + float(
        actual_on_demand.sum() * provider.on_demand_rate
    )
    baseline_cost = float(workload["demand"].sum() * provider.on_demand_rate)
    ladder = make_commitment_ladder(plan.commitment, len(workload), cycle_weeks, profile["ladder_share"])
    return {
        "provider": provider.name,
        "region": provider.region,
        "risk": risk,
        "risk_label": profile["label"],
        "error_percent": error_percent,
        "cycle_weeks": cycle_weeks,
        "offpeak": offpeak,
        "forecast_commitment": plan.commitment,
        "actual_cost": round(actual_cost, 2),
        "baseline_cost": round(baseline_cost, 2),
        "savings": round(baseline_cost - actual_cost, 2),
        "savings_percent": round((baseline_cost - actual_cost) / baseline_cost * 100, 2) if baseline_cost else 0.0,
        "on_demand_units": int(actual_on_demand.sum()),
        "quota_utilization": round(plan.commitment / provider.quota * 100, 1),
        "shadow_price_per_hour": round(plan.shadow_price_per_hour, 4),
        "quota_shadow_price": round(plan.quota_shadow_price, 4),
        "solver": plan.solver,
        "ladder": ladder.to_dict(orient="records"),
        "plan": plan.to_dict(),
        "scheduled": scheduled,
    }


def stress_test(workload: pd.DataFrame, provider: Provider, risk: str = "balanced",
                cycle_weeks: int = 4, offpeak: bool = True) -> pd.DataFrame:
    """Run the assignment's ±10%, ±25%, ±50% sensitivity cases."""
    rows = []
    for error in (-50, -25, -10, 0, 10, 25, 50):
        result = evaluate_scenario(workload, provider, error, risk, cycle_weeks, offpeak)
        rows.append({key: value for key, value in result.items() if key not in {"ladder", "plan", "scheduled"}})
    return pd.DataFrame(rows)
