"""Explainable capacity optimization with a PuLP ILP and a safe fallback."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
import pandas as pd

from .config import Provider

try:  # PuLP is optional so the demo still runs in a clean Python install.
    import pulp
except ImportError:  # pragma: no cover - exercised only without optional deps
    pulp = None


@dataclass
class OptimizationResult:
    provider: str
    region: str
    status: str
    commitment: int
    forecast_cost: float
    committed_cost: float
    on_demand_cost: float
    hourly_on_demand: list[int]
    hourly_capacity: list[int]
    shadow_price_per_hour: float
    quota_shadow_price: float
    solver: str

    @property
    def total_cost(self) -> float:
        return self.committed_cost + self.on_demand_cost

    def to_dict(self) -> dict:
        value = asdict(self)
        value["total_cost"] = round(self.total_cost, 2)
        return value


def _as_demand(values: Iterable[float]) -> np.ndarray:
    demand = np.ceil(np.asarray(list(values), dtype=float)).astype(int)
    if demand.ndim != 1 or len(demand) == 0:
        raise ValueError("demand must be a non-empty one-dimensional sequence")
    if np.any(demand < 0):
        raise ValueError("demand cannot be negative")
    return demand


def optimize_capacity(demand: Iterable[float], provider: Provider) -> OptimizationResult:
    """Minimize commitment plus hourly on-demand cost for one provider.

    The integer commitment variable makes the recommendation presentation-safe.
    The dual values are read from a continuous relaxation, which is the correct
    interpretation for the bottleneck diagnostic rather than pretending that an
    integer shadow price is exact.
    """
    values = _as_demand(demand)
    hours = len(values)

    if pulp is None:
        commitment = int(np.quantile(values, 0.70).round())
        commitment = min(commitment, provider.quota)
        od = np.maximum(values - commitment, 0).astype(int)
        committed_cost = commitment * hours * provider.committed_rate
        on_demand_cost = float(od.sum() * provider.on_demand_rate)
        return OptimizationResult(provider.name, provider.region, "Fallback", commitment,
                                  committed_cost + on_demand_cost, committed_cost,
                                  on_demand_cost, od.tolist(),
                                  (od + commitment).tolist(), 0.0, 0.0, "quantile fallback")

    model = pulp.LpProblem("CloudCompass_Commitment", pulp.LpMinimize)
    commitment = pulp.LpVariable("committed_capacity", lowBound=0, upBound=provider.quota, cat="Integer")
    on_demand = [pulp.LpVariable(f"on_demand_{h}", lowBound=0, cat="Integer") for h in range(hours)]
    model += commitment * hours * provider.committed_rate + pulp.lpSum(
        item * provider.on_demand_rate for item in on_demand
    )
    for h, target in enumerate(values):
        model += commitment + on_demand[h] >= int(target), f"demand_{h}"
    model.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[model.status] not in {"Optimal", "Feasible"}:
        raise RuntimeError(f"optimizer failed with status {pulp.LpStatus[model.status]}")

    chosen = int(round(commitment.value() or 0))
    od = [int(round(item.value() or 0)) for item in on_demand]
    committed_cost = chosen * hours * provider.committed_rate
    on_demand_cost = float(sum(od) * provider.on_demand_rate)

    relaxed = pulp.LpProblem("CloudCompass_ShadowPrices", pulp.LpMinimize)
    relaxed_commitment = pulp.LpVariable("committed_capacity", lowBound=0, upBound=provider.quota)
    relaxed_od = [pulp.LpVariable(f"on_demand_{h}", lowBound=0) for h in range(hours)]
    relaxed += relaxed_commitment * hours * provider.committed_rate + pulp.lpSum(
        item * provider.on_demand_rate for item in relaxed_od
    )
    demand_constraints = []
    for h, target in enumerate(values):
        constraint = relaxed_commitment + relaxed_od[h] >= int(target)
        relaxed += constraint, f"demand_{h}"
        demand_constraints.append(constraint)
    quota_constraint = relaxed_commitment <= provider.quota
    relaxed += quota_constraint, "quota"
    relaxed.solve(pulp.PULP_CBC_CMD(msg=False))
    hourly_duals = [abs(float(getattr(relaxed.constraints[f"demand_{h}"], "pi", 0.0) or 0.0)) for h in range(hours)]
    quota_dual = abs(float(getattr(relaxed.constraints["quota"], "pi", 0.0) or 0.0))

    return OptimizationResult(provider.name, provider.region, pulp.LpStatus[model.status], chosen,
                              committed_cost + on_demand_cost, committed_cost, on_demand_cost,
                              od, (np.asarray(od) + chosen).tolist(), float(max(hourly_duals, default=0)),
                              quota_dual, "PuLP/CBC ILP")


def compare_providers(demand: Iterable[float], providers: Iterable[Provider]) -> pd.DataFrame:
    """Return a ranked, presentation-friendly provider comparison."""
    rows = []
    for provider in providers:
        result = optimize_capacity(demand, provider)
        rows.append({
            "provider": provider.name,
            "region": provider.region,
            "commitment": result.commitment,
            "total_cost": round(result.total_cost, 2),
            "committed_cost": round(result.committed_cost, 2),
            "on_demand_cost": round(result.on_demand_cost, 2),
            "quota": provider.quota,
            "quota_utilization": round(result.commitment / provider.quota * 100, 1),
            "shadow_price": round(result.shadow_price_per_hour, 4),
            "solver": result.solver,
        })
    return pd.DataFrame(rows).sort_values("total_cost").reset_index(drop=True)
