# CloudCompass

Risk-aware cloud commitment and capacity simulator for a college project.

CloudCompass turns an hourly workload trace into an explainable cloud-capacity recommendation. It combines a PuLP/CBC integer optimization model with forecast-error stress tests, staggered commitment ladders, off-peak scheduling, provider comparison, and bottleneck diagnostics.

## Why this version is distinctive

- **Risk budget instead of one fixed answer:** choose a risk posture from conservative to aggressive; the optimizer changes how much capacity it commits.
- **Explainable recommendations:** every run produces a decision memo with the reason for the recommendation, not only a cost number.
- **Commitment laddering:** commitments can start in different weeks and expire on separate schedules, reducing lock-in.
- **Actionable bottlenecks:** quota pressure and hourly on-demand exposure are surfaced as named constraints.
- **Offline-first demo:** the included workload generator creates a reproducible trace, so the project runs without private cloud data.
- **Original “risk budget” workflow:** aggressive, balanced, and conservative profiles change the planned capacity buffer and the commitment ladder mix.

## Quick start

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python -m cloudcompass.cli --hours 168 --error 25 --risk balanced
```

Optional dashboard:

```bash
streamlit run cloudcompass/dashboard.py
```

The dashboard includes the assignment's seven forecast cases (-50%, -25%, -10%, 0%, +10%, +25%, +50%), a 4/8-week ladder switch, an off-peak scheduler, and a live decision memo.

If CBC/PuLP is unavailable, the CLI uses a deterministic quantile-based fallback and clearly labels the run. Install the requirements for the full ILP formulation and solver diagnostics.

## Project map

- `cloudcompass/data.py` - reproducible synthetic workload generation and validation
- `cloudcompass/optimizer.py` - ILP model plus safe fallback
- `cloudcompass/scenarios.py` - forecast error and strategy comparison
- `cloudcompass/scheduler.py` - off-peak shifting of delay-tolerant work
- `cloudcompass/analysis.py` - savings, risk, shadow-price, and decision-memo logic
- `cloudcompass/cli.py` - terminal demo and JSON export
- `cloudcompass/dashboard.py` - Streamlit interface
- `tests/test_core.py` - smoke tests for the core behavior

## Academic note

The workload is synthetic and deliberately transparent. Replace `generate_workload()` with a real trace adapter when a dataset is available. The project is intended as an educational simulator, not as a live cloud billing estimator.

