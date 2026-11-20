# CloudCompass - 24-hour college-project handoff

## What the assignment asks for

The brief asks for a cloud capacity simulator that combines:

1. A PuLP/CBC integer optimization model for reserved/committed and on-demand capacity.
2. Forecast-error experiments at ±10%, ±25%, and ±50%.
3. Staggered 4-week and 8-week commitment expiry schedules.
4. Off-peak scheduling for delay-tolerant work.
5. Shadow-price and quota bottleneck diagnostics.

CloudCompass implements all five requirements in one offline-first application.

## What makes this version distinct

- **Risk budget:** the user chooses aggressive, balanced, or conservative planning. The choice changes the buffer applied to the stressed forecast and the mix of core versus staggered commitments.
- **Decision memo:** the system explains the recommendation in plain language, including savings, quota pressure, error sensitivity, and the main bottleneck.
- **Provider comparison:** AWS, Azure, and GCP are compared with different rates, regions, and quotas instead of treating the cloud as a single generic provider.
- **Reproducible workload fingerprint:** the synthetic trace combines daily peaks, weekday/weekend behavior, a mild weekly wave, noise, and flexible work. The seed makes every demo repeatable.
- **Safe data boundary:** a real CSV can be supplied later, but the project still works without private Snowflake data.

## Suggested demo sequence

1. Run the dashboard with the default balanced profile.
2. Show the workload view and explain fixed versus flexible demand.
3. Change forecast error from 0% to +25% and show the risk curve.
4. Switch from a 4-week to an 8-week ladder and explain reduced lock-in.
5. Disable off-peak shifting and compare on-demand exposure.
6. Open Bottlenecks and explain quota utilization and shadow prices.
7. End with the decision memo: it is the model's recommendation in one paragraph.

## Commands

```powershell
cd outputs/cloudcompass
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m cloudcompass.cli --hours 168 --provider GCP --risk balanced --error 25 --json demo-report.json
streamlit run cloudcompass/dashboard.py
```

## Viva answers

**Why ILP?** Commitment is a discrete capacity decision, while hourly on-demand capacity fills the remaining demand. The objective minimizes committed cost plus on-demand spillover.

**Why stress testing?** A forecast can be wrong in either direction. Running the same plan over controlled error margins converts uncertainty into a visible cost-versus-risk curve.

**What is a shadow price?** It is the marginal value of relaxing a constraint in the continuous relaxation. A high value points to a quota or hourly demand constraint worth investigating.

**What is the limitation?** The default workload is synthetic and the prices are illustrative. The tool is an educational simulator, not a live cloud billing calculator.
