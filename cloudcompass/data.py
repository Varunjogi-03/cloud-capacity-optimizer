"""Workload creation and lightweight validation.

The generator intentionally uses an interpretable pattern: daily traffic, a
weekday/weekend effect, a mild seasonal wave, and a small amount of noise.
That makes the demo easy to explain in a viva while still behaving like a
real capacity-planning trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
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


SHAVED_ICE_COLUMNS = ("USAGE_HOUR", "REGION_NUM", "INSTANCE_TYPE", "NORM_USAGE")


def shaved_ice_series(path: str | Path) -> tuple[list[int], list[str]]:
    """Return the available region and VM-type choices in a Shaved Ice CSV."""
    frame = pd.read_csv(path, compression="infer", usecols=["REGION_NUM", "INSTANCE_TYPE"])
    regions = sorted(int(value) for value in frame["REGION_NUM"].dropna().unique())
    vm_types = sorted(str(value) for value in frame["INSTANCE_TYPE"].dropna().unique())
    return regions, vm_types


def load_shaved_ice_trace(
    path: str | Path,
    region: int,
    vm_type: str,
    hours: int | None = None,
    start_hour: int = 0,
    flexible_fraction: float = 0.22,
) -> pd.DataFrame:
    """Adapt one real Shaved Ice region/VM series to the dashboard schema.

    The public trace is normalized, so the resulting units are normalized VM
    units too. Missing timestamps are filled with zero demand to retain the
    actual time horizon and to account for idle commitment periods.
    """
    if start_hour < 0:
        raise ValueError("start_hour cannot be negative")
    if not 0 <= flexible_fraction <= 1:
        raise ValueError("flexible_fraction must be between 0 and 1")

    frame = pd.read_csv(path, compression="infer", usecols=list(SHAVED_ICE_COLUMNS))
    frame = frame[
        (frame["REGION_NUM"] == int(region))
        & (frame["INSTANCE_TYPE"].astype(str) == str(vm_type))
    ].copy()
    if frame.empty:
        raise ValueError(f"No Shaved Ice trace exists for region {region}, VM type {vm_type}.")

    frame["USAGE_HOUR"] = pd.to_datetime(frame["USAGE_HOUR"], errors="coerce")
    frame["NORM_USAGE"] = pd.to_numeric(frame["NORM_USAGE"], errors="coerce").fillna(0).clip(lower=0)
    frame = (
        frame.dropna(subset=["USAGE_HOUR"])
        .groupby("USAGE_HOUR", as_index=True)["NORM_USAGE"]
        .sum()
        .sort_index()
    )
    full_hours = pd.date_range(frame.index.min(), frame.index.max(), freq="h")
    frame = frame.reindex(full_hours, fill_value=0).iloc[start_hour:]
    if hours is not None:
        frame = frame.iloc[:hours]
    if frame.empty:
        raise ValueError("The selected Shaved Ice window contains no hours.")

    result = pd.DataFrame({"timestamp": frame.index, "demand": np.rint(frame.to_numpy()).astype(int)})
    result["hour_index"] = range(len(result))
    result["hour"] = result["timestamp"].dt.hour
    result["day_of_week"] = result["timestamp"].dt.dayofweek
    result["forecast"] = result["demand"].rolling(24, min_periods=1).mean().round().clip(lower=1).astype(int)
    result["flexible_demand"] = (result["demand"] * flexible_fraction).round().astype(int)
    result["fixed_demand"] = result["demand"] - result["flexible_demand"]
    validate_workload(result)
    return result

