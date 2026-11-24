"""Forecast stress tests, strategy comparison, and commitment laddering."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .config import LADDER_TERM_DISCOUNTS, RISK_PROFILES, Provider
from .data import apply_forecast_error, validate_workload
from .optimizer import OptimizationResult, optimize_capacity
from .scheduler import schedule_offpeak


def make_commitment_ladder(commitment: int, hours: int, cycle_weeks: int, ladder_share: float) -> pd.DataFrame:
    """Split a commitment into four blocks with genuinely staggered expiries."""
    if cycle_weeks not in (4, 8):
        raise ValueError("cycle_weeks must be 4 or 8")
    if commitment < 0:
        raise ValueError("commitment cannot be negative")
    blocks = 4
    long_term = int(round(commitment * ladder_share))
    short_term = max(0, commitment - long_term)
    base_capacity, remainder = divmod(short_term, blocks)
    weeks_per_block = cycle_weeks / blocks
    rows = []
    for index in range(blocks):
        rows.append({
            "block": f"ladder {index + 1}",
            "starts_week": 0,
            "expires_week": (index + 1) * weeks_per_block,
            "capacity": base_capacity + (1 if index < remainder else 0),
            "type": "staggered",
        })
    rows.insert(0, {"block": "core", "starts_week": 0, "expires_week": cycle_weeks,
                    "capacity": long_term, "type": "core commitment"})
    return pd.DataFrame(rows)


def ladder_capacity_by_hour(ladder: pd.DataFrame, hours: int) -> np.ndarray:
    """Return committed capacity available in each hour before blocks expire."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    capacity = np.zeros(hours, dtype=int)
    for row in ladder.itertuples(index=False):
        start = max(0, int(round(float(row.starts_week) * 7 * 24)))
        end = min(hours, int(round(float(row.expires_week) * 7 * 24)))
        if end > start:
            capacity[start:end] += int(row.capacity)
    return capacity


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
    term_discount = LADDER_TERM_DISCOUNTS[cycle_weeks]
    priced_provider = replace(provider, committed_rate=provider.committed_rate * (1 - term_discount))
    plan: OptimizationResult = optimize_capacity(target, priced_provider)
    ladder = make_commitment_ladder(plan.commitment, len(workload), cycle_weeks, profile["ladder_share"])
    committed_capacity = ladder_capacity_by_hour(ladder, len(workload))
    scheduled = schedule_offpeak(workload, pd.Series(committed_capacity, index=workload.index)) if offpeak else workload.copy()
    if not offpeak:
        scheduled["scheduled_demand"] = scheduled["demand"]
    evaluated_demand = scheduled["scheduled_demand"].to_numpy() if offpeak else workload["demand"].to_numpy()
    actual_on_demand = np.maximum(evaluated_demand - committed_capacity, 0)
    committed_cost = float(committed_capacity.sum() * priced_provider.committed_rate)
    actual_cost = committed_cost + float(actual_on_demand.sum() * provider.on_demand_rate)
    baseline_cost = float(workload["demand"].sum() * provider.on_demand_rate)
    return {
        "provider": provider.name,
        "region": provider.region,
        "risk": risk,
        "risk_label": profile["label"],
        "error_percent": error_percent,
        "cycle_weeks": cycle_weeks,
        "offpeak": offpeak,
        "forecast_commitment": plan.commitment,
        "committed_capacity_hours": int(committed_capacity.sum()),
        "committed_cost": round(committed_cost, 2),
        "term_discount_percent": round(term_discount * 100, 1),
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
