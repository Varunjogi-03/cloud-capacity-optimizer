import pandas as pd

from cloudcompass.analysis import build_decision_memo, rank_bottlenecks
from cloudcompass.config import DEFAULT_PROVIDERS
from cloudcompass.data import WorkloadConfig, generate_workload
from cloudcompass.optimizer import compare_providers, optimize_capacity
from cloudcompass.scenarios import evaluate_scenario, stress_test


def test_workload_is_reproducible_and_valid():
    a = generate_workload(WorkloadConfig(hours=48, seed=12))
    b = generate_workload(WorkloadConfig(hours=48, seed=12))
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 48
    assert (a["demand"] >= a["fixed_demand"]).all()


def test_optimizer_meets_demand():
    result = optimize_capacity([5, 10, 8], DEFAULT_PROVIDERS[0])
    assert result.commitment + min(result.hourly_on_demand) >= 5
    assert all(c >= d for c, d in zip(result.hourly_capacity, [5, 10, 8]))


def test_stress_and_memo_are_populated():
    workload = generate_workload(WorkloadConfig(hours=48))
    result = evaluate_scenario(workload, DEFAULT_PROVIDERS[2], 25, "balanced")
    stress = stress_test(workload, DEFAULT_PROVIDERS[2])
    assert set(stress["error_percent"]) == {-50, -25, -10, 0, 10, 25, 50}
    assert result["ladder"]
    assert build_decision_memo(result, stress)
    assert rank_bottlenecks(stress)


def test_provider_comparison_is_ranked():
    frame = compare_providers([8, 12, 18], DEFAULT_PROVIDERS)
    assert list(frame["total_cost"]) == sorted(frame["total_cost"])
