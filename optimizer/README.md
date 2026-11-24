# Phase 2: Baseline Mathematical Model Formulation

This document summarizes everything implemented, verified, and added during **Phase 2** of the **Cloud Commitment & Capacity Simulator** (`cloud-capacity-optimizer`). Phase 2 establishes the core Integer Linear Programming (ILP) cost-minimization engine using **PuLP 4.x** and the **CBC** solver, integrated with Phase 1 hourly workload traces from Snowflake's Shaved Ice dataset.

---

## What Was Added

```text
cloud-capacity-optimizer/
└── optimizer/
    ├── baseline_ilp.py            # Core PuLP 4.x + CBC ILP/LP optimization engine
    └── run_phase2_baseline.py     # CLI runner & Phase 1 Shaved Ice CSV adapter
```

### 1. Core Optimization Engine (`optimizer/baseline_ilp.py`)
* **Structured Data Models:** Added Malloovia-inspired dataclasses (`InstancePricing`, `QuotaConfig`, and `OptimizationResult`) to cleanly separate pricing inputs, capacity limits, and structured solver outputs.
* **`BaselineCapacityOptimizer` Solver:** Formulates and solves the baseline cost-minimization ILP over hourly demand traces, computing total spend, reserved vs. on-demand cost splits, savings against pure On-Demand usage, reserved utilization, idle commitment waste, and an hour-by-hour dispatch table.
* **Built-In Self-Test (`__main__`):** Added an executable 30-day synthetic diurnal workload test that verifies the CBC integer solution against the closed-form analytical newsvendor quantile.

### 2. Phase 1 Data Adapter & CLI Runner (`optimizer/run_phase2_baseline.py`)
* **Shaved Ice Schema Mapping:** Ingests the Phase 1 CSV format (`USAGE_HOUR`, `REGION_NUM`, `INSTANCE_TYPE`, `NORM_USAGE`), normalizes column types, aggregates any duplicate entries, and pads missing calendar hours with zero demand so reserved capacity is billed accurately across the entire horizon.
* **Exact Per-Region Decomposition:** Solves each region independently to preserve global optimality while reducing CBC solve times on multi-month and full-year traces.
* **Flexible Pricing & Filtering:** Supports date-range slicing (`--start`, `--end`), configurable commitment discounts (`--discount`, default `0.40`), and optional custom per-instance On-Demand rate overrides (`--pricing-json`).
* **Baseline Artifact Export:** Automatically writes locked baseline CSVs to `results/phase2/` for downstream benchmarking in Phases 3 through 5.

---

## Mathematical Formulation

### Sets & Parameters
* $t \in \mathcal{T} = \{1, \dots, T\}$: Hourly time slots across the planning horizon.
* $r \in \mathcal{R}$: Cloud regions (`REGION_NUM`).
* $v \in \mathcal{V}$: Virtual machine classes (`INSTANCE_TYPE`).
* $D_{r,v,t} \in \mathbb{Z}_{\ge 0}$: Hourly normalized compute demand (`NORM_USAGE`).
* $c^{\text{od}}_{r,v} > 0$: Hourly On-Demand rate per instance.
* $c^{\text{res}}_{r,v} > 0$: Effective hourly Reserved Instance / Savings Plan rate ($c^{\text{res}}_{r,v} < c^{\text{od}}_{r,v}$).
* $Q^{\text{reg}}_{r}$ and $Q^{\text{vm}}_{r,v}$: Optional regional aggregate quotas and per-instance-class limits.

### Decision Variables
* $R_{r,v} \in \mathbb{Z}_{\ge 0}$: Long-term reserved instance count committed over all $T$ hours.
* $O_{r,v,t} \in \mathbb{Z}_{\ge 0}$: Hourly On-Demand instance count provisioned at hour $t$.

### Objective Function
Minimize total cloud compute expenditure across the planning horizon:

$$\min Z = \sum_{r \in \mathcal{R}} \sum_{v \in \mathcal{V}} \left( T \cdot c^{\text{res}}_{r,v} \cdot R_{r,v} + \sum_{t \in \mathcal{T}} c^{\text{od}}_{r,v} \cdot O_{r,v,t} \right)$$

### Constraints
1. **Strict Hourly Demand Satisfaction:**
   $$R_{r,v} + O_{r,v,t} \ge D_{r,v,t} \qquad \forall r \in \mathcal{R},\; v \in \mathcal{V},\; t \in \mathcal{T}$$
2. **Optional Regional Quotas** (Malloovia `LimitingSet` equivalent):
   $$\sum_{v \in \mathcal{V}} \left( R_{r,v} + O_{r,v,t} \right) \le Q^{\text{reg}}_{r} \qquad \forall r \in \mathcal{R},\; t \in \mathcal{T}$$
3. **Optional Instance-Class Limits:**
   $$R_{r,v} + O_{r,v,t} \le Q^{\text{vm}}_{r,v} \qquad \forall r \in \mathcal{R},\; v \in \mathcal{V},\; t \in \mathcal{T}$$

### Analytical Verification (Critical Fractile)
When capacity quotas are non-binding, the unconstrained optimal reservation $R^*_{r,v}$ satisfies the newsvendor critical fractile:

$$R^*_{r,v} = F^{-1}_{D_{r,v}}\!\left(1 - \frac{c^{\text{res}}_{r,v}}{c^{\text{od}}_{r,v}}\right)$$

---

## Key Engineering Updates Made During Phase 2

* **Portable CBC execution:** Uses `pulp.PULP_CBC_CMD`, which invokes the CBC executable bundled with PuLP. This avoids requiring a separate system-wide `cbc.exe` installation.
* **Column-Order-Safe Ingestion:** Replaced positional `itertuples` indexing with explicit column selection via NumPy arrays so input files work regardless of CSV column ordering.

---

## Forward-Compatibility Hooks for Phases 3–5

To avoid refactoring the core solver in later phases, two hooks were built directly into `BaselineCapacityOptimizer.solve()`:

* **`fixed_reserved` (Phase 3 — Uncertainty & Risk Modeling):** Locks reserved allocations optimized on forecast-perturbed traces ($\pm 10\%$, $\pm 25\%$, $\pm 50\%$) so the solver can immediately evaluate realized On-Demand spillover and idle waste on ground-truth traces.
* **`relax=True` (Phase 5 — Shadow Pricing & Bottleneck Diagnosis):** Relaxes decision variables from `LpInteger` to `LpContinuous` and collects non-zero `.pi` dual values from named `RegQuota_*` and `VMQuota_*` constraints.

---

## Verification Results

Running the built-in 30-day synthetic diurnal self-test (`python optimizer/baseline_ilp.py`) with a $40\%$ commitment discount ($c^{\text{od}} = \$1.00$, $c^{\text{res}} = \$0.60$) produced an exact match to the analytical newsvendor quantile:

| Metric | Value |
| :--- | :--- |
| **Solver Status** | `Optimal` |
| **Optimal Reserved Capacity ($R$)** | `17.0` |
| **Analytical 40th-Percentile Quantile** | `17.00` |
| **Pure On-Demand Cost** | `$14,269.00` |
| **Optimized Total Cost** | `$10,937.00` |
| **Reserved Cost** | `$7,344.00` |
| **On-Demand Spillover Cost** | `$3,593.00` |
| **Net Cost Savings** | `$3,332.00` (`23.35%`) |
| **Reserved Utilization** | `87.22%` |

---

## How to Run

### 1. Install Dependencies
```bash
pip install "pulp[cbc]" pandas numpy
```

### 2. Run the Built-In Self-Test
```bash
python optimizer/baseline_ilp.py
```

### 3. Run Against the Phase 1 Shaved Ice Dataset
```bash
# Fast 1-month validation slice
python optimizer/run_phase2_baseline.py \
  --data path/to/shaved_ice.csv \
  --start 2021-02-01 \
  --end 2021-03-01 \
  --discount 0.40

# Full horizon run
python optimizer/run_phase2_baseline.py \
  --data path/to/shaved_ice.csv \
  --discount 0.40
```

### Generated Output Artifacts (`results/phase2/`)
* `phase2_region_summary.csv` — Per-region Pure On-Demand cost, Optimized cost, Reserved/On-Demand split, idle commitment cost, savings %, utilization %, and CBC solve time.
* `phase2_reserved_allocations.csv` — Optimal reserved instance counts ($R_{r,v}$), mean/peak demand, mean On-Demand spillover, and mean idle capacity per `(Region, VM Type)`.
* `phase2_hourly_dispatch.csv` — Complete hour-by-hour demand, reserved usage, On-Demand dispatch, idle capacity, and hourly expenditure log.
