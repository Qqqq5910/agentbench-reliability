import pandas as pd

from benchtrust.statistics import (
    bootstrap_leaderboard,
    paired_difference_interval,
    score_interval,
    task_summary,
)


def test_score_interval_is_reproducible() -> None:
    outcomes = [1, 1, 0, 1, 0, 1]
    first = score_interval(outcomes, n_boot=500, seed=7)
    second = score_interval(outcomes, n_boot=500, seed=7)
    assert first == second
    assert first.lower <= first.estimate <= first.upper


def test_identical_paired_outcomes_have_zero_difference() -> None:
    result = paired_difference_interval([1, 0, 1, 1], [1, 0, 1, 1], n_boot=500, seed=3)
    assert result.estimate == 0.0
    assert result.lower == 0.0
    assert result.upper == 0.0


def test_bootstrap_leaderboard_preserves_clear_ordering() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A"] * 4 + ["B"] * 4,
            "task_id": ["t1", "t2", "t3", "t4"] * 2,
            "resolved": [1, 1, 1, 1, 0, 0, 0, 0],
        }
    )
    summary, pairwise = bootstrap_leaderboard(frame, n_boot=500, seed=11)
    assert summary.loc[0, "system_id"] == "A"
    assert summary.loc[0, "top1_probability"] == 1.0
    assert pairwise.loc["A", "B"] == 1.0
    assert pairwise.loc["B", "A"] == 0.0


def test_task_summary_peaks_at_half_solve_rate() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A", "B", "A", "B"],
            "task_id": ["easy", "easy", "split", "split"],
            "resolved": [1, 1, 1, 0],
        }
    )
    result = task_summary(frame).set_index("task_id")
    assert result.loc["easy", "disagreement"] == 0.0
    assert result.loc["split", "disagreement"] == 1.0
    assert result.loc["split", "entropy_bits"] == 1.0
