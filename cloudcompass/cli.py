"""Command-line demo for CloudCompass."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import build_decision_memo, rank_bottlenecks
from .config import DEFAULT_PROVIDERS, RISK_PROFILES
from .data import WorkloadConfig, generate_workload, load_trace_csv
from .scenarios import evaluate_scenario, stress_test


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudCompass risk-aware capacity simulator")
    parser.add_argument("--hours", type=int, default=168)
    parser.add_argument("--error", type=int, default=0, choices=(-50, -25, -10, 0, 10, 25, 50))
    parser.add_argument("--risk", choices=tuple(RISK_PROFILES), default="balanced")
    parser.add_argument("--cycle-weeks", type=int, choices=(4, 8), default=4)
    parser.add_argument("--provider", default="GCP", choices=tuple(p.name for p in DEFAULT_PROVIDERS))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    workload = load_trace_csv(str(args.csv), hours=args.hours) if args.csv else generate_workload(WorkloadConfig(hours=args.hours))
    provider = next(p for p in DEFAULT_PROVIDERS if p.name == args.provider)
    result = evaluate_scenario(workload, provider, args.error, args.risk, args.cycle_weeks)
    stress = stress_test(workload, provider, args.risk, args.cycle_weeks)
    payload = {"recommendation": {k: v for k, v in result.items() if k not in {"scheduled"}},
               "stress_test": stress.to_dict(orient="records"),
               "bottlenecks": rank_bottlenecks(stress),
               "decision_memo": build_decision_memo(result, stress)}
    print(build_decision_memo(result, stress))
    print(f"\nProvider: {provider.name} | commitment: {result['forecast_commitment']} units | "
          f"cost: ${result['actual_cost']:,.2f} | savings: {result['savings_percent']:.2f}%")
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"Saved report to {args.json}")


if __name__ == "__main__":
    main()
