import pandas as pd

from benchtrust.stage2 import (
    build_execution_manifest,
    recommend_replicates,
    select_pilot_tasks,
    select_stage2_tasks,
    simulate_replicate_design,
)


def _task_summary(n: int = 60) -> pd.DataFrame:
    rows = []
    for index in range(n):
        repository = "repo_a" if index < n // 2 else "repo_b"
        rows.append(
            {
                "task_id": f"{repository}__task-{index}",
                "solve_rate": 0.1 + 0.8 * index / max(n - 1, 1),
                "n_systems": 10,
                "disagreement": 0.95 if index % 3 == 0 else 0.5,
                "entropy_bits": 0.8,
            }
        )
    return pd.DataFrame(rows)


def test_stage2_task_selection_is_reproducible_and_complete() -> None:
    frame = _task_summary()
    first = select_stage2_tasks(
        frame,
        total_tasks=24,
        representative_tasks=16,
        enriched_tasks=8,
        disagreement_threshold=0.9,
        seed=17,
    )
    second = select_stage2_tasks(
        frame,
        total_tasks=24,
        representative_tasks=16,
        enriched_tasks=8,
        disagreement_threshold=0.9,
        seed=17,
    )
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 24
    assert first["task_id"].nunique() == 24
    assert (first["selection_component"] == "representative").sum() == 16
    enriched = first[first["selection_component"] == "high_disagreement_enrichment"]
    assert len(enriched) == 8
    assert (enriched["disagreement"] >= 0.9).all()


def test_replicate_design_simulation_is_reproducible() -> None:
    frame = _task_summary(40)
    first = simulate_replicate_design(
        frame,
        candidate_replicates=[3, 5],
        scenarios={"moderate": 1.0},
        n_sim=200,
        seed=23,
    )
    second = simulate_replicate_design(
        frame,
        candidate_replicates=[3, 5],
        scenarios={"moderate": 1.0},
        n_sim=200,
        seed=23,
    )
    pd.testing.assert_frame_equal(first, second)
    assert first["true_score_difference"].round(8).eq(0.03).all()


def test_recommendation_uses_smallest_candidate_meeting_thresholds() -> None:
    frame = pd.DataFrame(
        {
            "scenario": ["moderate", "moderate", "high"],
            "replicates": [3, 5, 5],
            "score_abs_error_p95": [0.04, 0.02, 0.05],
            "run_sd_median_relative_error": [0.4, 0.2, 0.4],
            "paired_diff_ci_median_halfwidth": [0.05, 0.03, 0.05],
            "unstable_detection_mean": [0.7, 0.9, 0.7],
            "rank_reversal_median_abs_error": [0.2, 0.1, 0.2],
        }
    )
    thresholds = {
        "score_abs_error_p95": 0.03,
        "run_sd_median_relative_error": 0.3,
        "paired_diff_ci_median_halfwidth": 0.04,
        "unstable_detection_mean": 0.8,
        "rank_reversal_median_abs_error": 0.15,
    }
    recommendation, annotated = recommend_replicates(
        frame,
        primary_scenario="moderate",
        thresholds=thresholds,
    )
    assert recommendation == 5
    assert annotated.loc[1, "meets_primary_precision"]


def test_pilot_tasks_are_reproducible_and_disjoint() -> None:
    frame = _task_summary(80)
    formal = select_stage2_tasks(
        frame,
        total_tasks=24,
        representative_tasks=16,
        enriched_tasks=8,
        disagreement_threshold=0.9,
        seed=17,
    )
    first = select_pilot_tasks(frame, formal, n_tasks=10, seed=19)
    second = select_pilot_tasks(frame, formal, n_tasks=10, seed=19)

    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 10
    assert first["task_id"].nunique() == 10
    assert not set(first["task_id"]) & set(formal["task_id"])
    assert first["selection_component"].eq("pilot_excluded_from_confirmatory").all()


def test_execution_manifest_is_complete_unique_and_reproducible() -> None:
    tasks = _task_summary(4)
    systems = [
        {"system_id": "A", "scaffold": "one", "repository": "org/one", "commit": "abc"},
        {"system_id": "B", "scaffold": "two", "repository": "org/two", "commit": "def"},
    ]
    model = {"provider": "test", "model_id": "model", "reasoning_effort": "medium"}
    first = build_execution_manifest(
        tasks, systems, replicates=2, seed=31, phase="pilot", common_model=model
    )
    second = build_execution_manifest(
        tasks, systems, replicates=2, seed=31, phase="pilot", common_model=model
    )

    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 16
    assert first["run_id"].nunique() == 16
    assert first["execution_order"].tolist() == list(range(1, 17))
    assert set(first["system_id"]) == {"A", "B"}
    assert set(first["replicate_index"]) == {1, 2}
