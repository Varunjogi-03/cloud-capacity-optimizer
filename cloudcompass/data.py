"""Workload creation and lightweight validation.

The generator intentionally uses an interpretable pattern: daily traffic, a
weekday/weekend effect, a mild seasonal wave, and a small amount of noise.
That makes the demo easy to explain in a viva while still behaving like a
real capacity-planning trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import random

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WorkloadConfig:
    hours: int = 168
    seed: int = 7
    starting_demand: int = 18
    peak_amplitude: int = 16
    flexible_fraction: float = 0.22


def generate_workload(config: WorkloadConfig = WorkloadConfig()) -> pd.DataFrame:
    """Return a reproducible hourly workload with forecast and flexible work."""
    if config.hours < 24:
        raise ValueError("hours must be at least 24")
    if not 0 <= config.flexible_fraction <= 1:
        raise ValueError("flexible_fraction must be between 0 and 1")

    rng = random.Random(config.seed)
    start = datetime(2026, 1, 5, 0, 0)  # Monday: easier charts and explanations.
    rows = []
    for index in range(config.hours):
        timestamp = start + timedelta(hours=index)
        hour = timestamp.hour
        dow = timestamp.weekday()
        rush = math.sin(math.pi * (hour - 6) / 16) if 6 <= hour <= 22 else 0
        rush = max(0.0, rush)
        weekend_factor = 0.72 if dow >= 5 else 1.0
        long_wave = 1 + 0.10 * math.sin(2 * math.pi * index / (24 * 7))
        noise = rng.uniform(-1.8, 1.8)
        demand = max(4, round((config.starting_demand + config.peak_amplitude * rush) * weekend_factor * long_wave + noise))
        flexible = max(0, round(demand * config.flexible_fraction))
        # Forecast is intentionally imperfect but correlated with demand.
        forecast_noise = rng.uniform(-0.07, 0.07)
        forecast = max(1, round(demand * (1 + forecast_noise)))
        rows.append({
            "timestamp": timestamp,
            "hour_index": index,
            "hour": hour,
            "day_of_week": dow,
            "demand": demand,
            "forecast": forecast,
            "flexible_demand": flexible,
            "fixed_demand": demand - flexible,
        })
    return pd.DataFrame(rows)


def apply_forecast_error(workload: pd.DataFrame, error_percent: int) -> pd.Series:
    """Return forecast demand after a deterministic stress-test error."""
    if error_percent not in (-50, -25, -10, 0, 10, 25, 50):
        raise ValueError("error_percent must be one of -50, -25, -10, 0, 10, 25, 50")
    return np.maximum(1, np.rint(workload["forecast"] * (1 + error_percent / 100))).astype(int)


def validate_workload(workload: pd.DataFrame) -> None:
    required = {"timestamp", "hour_index", "demand", "forecast", "flexible_demand"}
    missing = sorted(required - set(workload.columns))
    if missing:
        raise ValueError(f"workload is missing columns: {missing}")
    if workload.empty:
        raise ValueError("workload cannot be empty")
    if (workload[["demand", "forecast", "flexible_demand"]] < 0).any().any():
        raise ValueError("workload values cannot be negative")


def load_trace_csv(path: str, demand_column: str = "demand", hours: int | None = None) -> pd.DataFrame:
    """Load a simple hourly CSV and adapt it to CloudCompass columns.

    This keeps the demo compatible with a real trace later, while retaining a
    transparent synthetic fallback for a reproducible college presentation.
    """
    frame = pd.read_csv(path)
    if demand_column not in frame.columns:
        raise ValueError(f"CSV must contain '{demand_column}'")
    demand = pd.to_numeric(frame[demand_column], errors="coerce").fillna(0).clip(lower=0)
    if hours:
        demand = demand.iloc[:hours]
    if demand.empty:
        raise ValueError("CSV contains no usable demand rows")
    start = pd.Timestamp("2026-01-05")
    timestamps = pd.date_range(start, periods=len(demand), freq="h")
    result = pd.DataFrame({"timestamp": timestamps, "hour_index": range(len(demand)), "demand": demand.to_numpy()})
    result["hour"] = result["timestamp"].dt.hour
    result["day_of_week"] = result["timestamp"].dt.dayofweek
    result["forecast"] = result["demand"].rolling(6, min_periods=1).mean().round().clip(lower=1).astype(int)
    result["flexible_demand"] = (result["demand"] * 0.22).round().astype(int)
    result["fixed_demand"] = result["demand"] - result["flexible_demand"]
    validate_workload(result)
    return result

