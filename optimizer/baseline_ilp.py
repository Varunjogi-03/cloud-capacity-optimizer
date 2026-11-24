from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd
import pulp


@dataclass(frozen=True)
class InstancePricing:
    """Hourly pricing for a (region, vm_type) class."""
    region: int
    vm_type: str
    on_demand_rate: float
    reserved_rate: float

    def __post_init__(self) -> None:
        if not (0 < self.reserved_rate < self.on_demand_rate):
            raise ValueError(
                f"Invalid pricing for ({self.region}, {self.vm_type}): "
                "reserved_rate must be strictly positive and less than on_demand_rate."
            )


@dataclass(frozen=True)
class QuotaConfig:
    """Optional regional and per-instance-class capacity limits."""
    regional_limits: Dict[int, int] = field(default_factory=dict)
    vm_limits: Dict[Tuple[int, str], int] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    status: str
    total_cost: float
    reserved_cost: float
    on_demand_cost: float
    pure_on_demand_cost: float
    savings_usd: float
    savings_pct: float
    reserved_utilization_pct: float
    idle_commitment_cost: float
    reserved_allocation: Dict[Tuple[int, str], float]
    hourly_dispatch: pd.DataFrame
    shadow_prices: Dict[str, float]


class BaselineCapacityOptimizer:
    """
    Phase 2 Baseline ILP Cost-Minimization Engine (PuLP + CBC).

    Expected demand_df schema (aligned with Snowflake Shaved Ice):
        Columns: ['Timestamp', 'Region', 'VM Type', 'Count']
    """

    def __init__(
        self,
        pricing: Dict[Tuple[int, str], InstancePricing],
        quotas: Optional[QuotaConfig] = None,
    ) -> None:
        self.pricing = pricing
        self.quotas = quotas or QuotaConfig()

    def solve(
        self,
        demand_df: pd.DataFrame,
        *,
        relax: bool = False,
        fixed_reserved: Optional[Dict[Tuple[int, str], float]] = None,
        solver_msg: bool = False,
        time_limit_sec: Optional[int] = None,
    ) -> OptimizationResult:
        required_cols = {"Timestamp", "Region", "VM Type", "Count"}
        missing = required_cols - set(demand_df.columns)
        if missing:
            raise ValueError(f"demand_df is missing required columns: {missing}")

        # Build dense hourly index per (Region, VM Type) so idle hours are priced accurately
        df = demand_df.copy()
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        timestamps = sorted(df["Timestamp"].unique())
        horizon_hours = len(timestamps)
        time_idx = {ts: idx for idx, ts in enumerate(timestamps)}

        pairs = sorted(
            {(int(r), str(v)) for r, v in zip(df["Region"], df["VM Type"])}
        )
        regions = sorted({r for r, _ in pairs})

        for pair in pairs:
            if pair not in self.pricing:
                raise KeyError(f"Missing pricing entry for (Region, VM Type) = {pair}")

        # Column-order-safe mapping: (r, v, t) -> integer demand
        demand_map: Dict[Tuple[int, str, int], int] = {
            (r, v, t): 0 for (r, v) in pairs for t in range(horizon_hours)
        }
        for reg, vm, ts, cnt in df[["Region", "VM Type", "Timestamp", "Count"]].to_numpy():
            demand_map[(int(reg), str(vm), time_idx[ts])] = int(cnt)

        var_cat = pulp.LpContinuous if relax else pulp.LpInteger
        prob = pulp.LpProblem("CloudCapacityBaseline", pulp.LpMinimize)

        # 1. Decision Variables (PuLP 4.x API)
        R: Dict[Tuple[int, str], pulp.LpVariable] = {}
        for r, v in pairs:
            if fixed_reserved is not None and (r, v) in fixed_reserved:
                val = fixed_reserved[(r, v)]
                R[(r, v)] = prob.add_variable(
                    f"R_r{r}_{v}", lowBound=val, upBound=val, cat=var_cat
                )
            else:
                R[(r, v)] = prob.add_variable(
                    f"R_r{r}_{v}", lowBound=0, cat=var_cat
                )

        O: Dict[Tuple[int, str, int], pulp.LpVariable] = {
            (r, v, t): prob.add_variable(f"O_r{r}_{v}_t{t}", lowBound=0, cat=var_cat)
            for (r, v) in pairs
            for t in range(horizon_hours)
        }

        # 2. Objective Function: Minimize Reserved + Hourly On-Demand Spend
        reserved_expr = pulp.lpSum(
            horizon_hours * self.pricing[(r, v)].reserved_rate * R[(r, v)]
            for (r, v) in pairs
        )
        on_demand_expr = pulp.lpSum(
            self.pricing[(r, v)].on_demand_rate * O[(r, v, t)]
            for (r, v) in pairs
            for t in range(horizon_hours)
        )
        prob += reserved_expr + on_demand_expr, "Total_Cloud_Spend"

        # 3. Constraints
        # 3a. Strict Hourly Demand Satisfaction
        for (r, v) in pairs:
            for t in range(horizon_hours):
                d_val = demand_map[(r, v, t)]
                prob += (
                    R[(r, v)] + O[(r, v, t)] >= d_val,
                    f"Demand_r{r}_{v}_t{t}",
                )

        # 3b. Instance-Class Quotas (Optional)
        for (r, v), limit in self.quotas.vm_limits.items():
            if (r, v) not in R:
                continue
            for t in range(horizon_hours):
                prob += (
                    R[(r, v)] + O[(r, v, t)] <= limit,
                    f"VMQuota_r{r}_{v}_t{t}",
                )

        # 3c. Regional Quotas (Optional - Malloovia LimitingSet equivalent)
        for r, limit in self.quotas.regional_limits.items():
            if r not in regions:
                continue
            region_vms = [v for (reg, v) in pairs if reg == r]
            for t in range(horizon_hours):
                prob += (
                    pulp.lpSum(R[(r, v)] + O[(r, v, t)] for v in region_vms) <= limit,
                    f"RegQuota_r{r}_t{t}",
                )

        # 4. Solve with PuLP's bundled CBC executable. COIN_CMD depends on a
        # system-wide cbc.exe and fails in a normal virtual environment.
        solver_kwargs: Dict[str, object] = {"msg": solver_msg}
        if time_limit_sec is not None:
            solver_kwargs["timeLimit"] = time_limit_sec
        solver = pulp.PULP_CBC_CMD(**solver_kwargs)

        prob.solve(solver)
        status = pulp.LpStatus.get(prob.status, str(prob.status))

        if status != "Optimal":
            raise RuntimeError(
                f"Optimization failed with status '{status}'. "
                "Check if quota limits are below peak hourly demand."
            )

        # 5. Extract Metrics & Dispatch Schedule
        reserved_alloc = {(r, v): float(pulp.value(R[(r, v)])) for (r, v) in pairs}
        records = []
        pure_od_cost = 0.0
        idle_cost = 0.0
        total_reserved_capacity_hrs = 0.0
        used_reserved_capacity_hrs = 0.0

        for (r, v) in pairs:
            p = self.pricing[(r, v)]
            r_val = reserved_alloc[(r, v)]
            for t, ts in enumerate(timestamps):
                d_val = demand_map[(r, v, t)]
                o_val = float(pulp.value(O[(r, v, t)]))
                used_r = min(r_val, d_val)
                idle_r = max(0.0, r_val - d_val)

                pure_od_cost += d_val * p.on_demand_rate
                idle_cost += idle_r * p.reserved_rate
                total_reserved_capacity_hrs += r_val
                used_reserved_capacity_hrs += used_r

                records.append(
                    {
                        "Timestamp": ts,
                        "Region": r,
                        "VM Type": v,
                        "Demand": d_val,
                        "Reserved": r_val,
                        "OnDemand": o_val,
                        "IdleReserved": idle_r,
                        "HourlyCost": r_val * p.reserved_rate + o_val * p.on_demand_rate,
                    }
                )

        reserved_cost = float(pulp.value(reserved_expr))
        on_demand_cost = float(pulp.value(on_demand_expr))
        total_cost = reserved_cost + on_demand_cost
        savings_usd = pure_od_cost - total_cost
        savings_pct = (savings_usd / pure_od_cost * 100.0) if pure_od_cost > 0 else 0.0
        utilization_pct = (
            used_reserved_capacity_hrs / total_reserved_capacity_hrs * 100.0
            if total_reserved_capacity_hrs > 0
            else 0.0
        )

        # Shadow prices are valid only when solving the LP relaxation (relax=True)
        shadow_prices: Dict[str, float] = {}
        if relax:
            for name, constraint in prob.constraints.items():
                if (name.startswith("RegQuota_") or name.startswith("VMQuota_")) and constraint.pi:
                    if abs(constraint.pi) > 1e-6:
                        shadow_prices[name] = float(constraint.pi)

        return OptimizationResult(
            status=status,
            total_cost=total_cost,
            reserved_cost=reserved_cost,
            on_demand_cost=on_demand_cost,
            pure_on_demand_cost=pure_od_cost,
            savings_usd=savings_usd,
            savings_pct=savings_pct,
            reserved_utilization_pct=utilization_pct,
            idle_commitment_cost=idle_cost,
            reserved_allocation=reserved_alloc,
            hourly_dispatch=pd.DataFrame(records),
            shadow_prices=shadow_prices,
        )


if __name__ == "__main__":
    # --- Option A: Quick self-test with synthetic 30-day hourly demand ---
    rng = np.random.default_rng(42)
    hours = pd.date_range("2026-01-01", periods=24 * 30, freq="h")

    # Diurnal wave + noise to mimic Shaved Ice workload patterns
    diurnal = 20 + 10 * np.sin(2 * np.pi * np.arange(len(hours)) / 24)
    counts = np.maximum(1, np.round(diurnal + rng.normal(0, 4, size=len(hours)))).astype(int)

    demand_df = pd.DataFrame(
        {
            "Timestamp": hours,
            "Region": 1,
            "VM Type": "A",
            "Count": counts,
        }
    )

    # --- Option B: Load your Phase 1 output instead (uncomment & adjust path) ---
    # demand_df = pd.read_csv("data/phase1_workload.csv")
    # demand_df = pd.read_parquet("data/hourly_normalized.parquet")

    pricing = {
        (1, "A"): InstancePricing(
            region=1,
            vm_type="A",
            on_demand_rate=1.00,
            reserved_rate=0.60,  # 40% commitment discount
        )
    }

    optimizer = BaselineCapacityOptimizer(pricing=pricing)
    result = optimizer.solve(demand_df, solver_msg=False)

    # Analytical newsvendor verification (40th percentile for 40% discount)
    expected_r = np.quantile(counts, 1.0 - (0.60 / 1.00))

    print(f"Status:                {result.status}")
    print(f"Optimal Reserved R:    {result.reserved_allocation}")
    print(f"Analytical Quantile:   {expected_r:.2f}")
    print(f"Pure On-Demand Cost:   ${result.pure_on_demand_cost:,.2f}")
    print(f"Optimized Total Cost:  ${result.total_cost:,.2f}")
    print(f"  - Reserved Cost:     ${result.reserved_cost:,.2f}")
    print(f"  - On-Demand Cost:    ${result.on_demand_cost:,.2f}")
    print(f"Savings:               ${result.savings_usd:,.2f} ({result.savings_pct:.2f}%)")
    print(f"Reserved Utilization:  {result.reserved_utilization_pct:.2f}%")
    print("\nFirst 5 hourly dispatch rows:")
    print(result.hourly_dispatch.head())
