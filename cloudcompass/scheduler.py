"""Off-peak scheduling for delay-tolerant workload."""

from __future__ import annotations

import pandas as pd


def schedule_offpeak(workload: pd.DataFrame, capacity: pd.Series) -> pd.DataFrame:
    """Shift flexible demand into spare committed capacity where possible.

    The algorithm is deliberately explainable: fixed demand remains at its
    original hour; flexible demand is placed in the lowest fixed-demand hours
    of the same day first. The function never changes total work and never
    schedules more than the supplied committed capacity.
    """
    if len(workload) != len(capacity):
        raise ValueError("capacity must have one value per workload row")
    frame = workload.copy().reset_index(drop=True)
    cap = pd.Series(capacity).reset_index(drop=True).astype(float)
    frame["scheduled_demand"] = frame["fixed_demand"].astype(float)
    frame["shifted_in"] = 0.0
    frame["shifted_out"] = 0.0

    for _, day in frame.groupby(frame["timestamp"].dt.date, sort=False):
        indices = list(day.index)
        # Put flexible tasks into hours with the most spare room first.
        targets = sorted(indices, key=lambda idx: (frame.at[idx, "fixed_demand"], frame.at[idx, "hour"]))
        for source in indices:
            remaining = float(frame.at[source, "flexible_demand"])
            if remaining <= 0:
                continue
            for target in targets:
                spare = max(0.0, cap.iloc[target] - frame.at[target, "scheduled_demand"])
                moved = min(remaining, spare)
                if moved <= 0:
                    continue
                frame.at[target, "scheduled_demand"] += moved
                frame.at[target, "shifted_in"] += moved
                remaining -= moved
                if target != source:
                    frame.at[source, "shifted_out"] += moved
                if remaining <= 0:
                    break
            # Work that cannot fit stays at its source hour and is paid on demand.
            if remaining > 0:
                frame.at[source, "scheduled_demand"] += remaining
    frame["scheduled_demand"] = frame["scheduled_demand"].round().astype(int)
    return frame

