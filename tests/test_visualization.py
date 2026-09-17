from pathlib import Path

import pandas as pd

from benchtrust.visualization import (
    plot_pairwise_ordering,
    plot_power_curve,
    plot_rank_intervals,
    plot_score_intervals,
    plot_task_disagreement,
)


def test_stage1_plots_write_nonempty_pngs(tmp_path: Path) -> None:
    leaderboard = pd.DataFrame(
        {
            "system_id": ["A", "B"],
            "score": [0.8, 0.7],
            "score_ci_lower": [0.72, 0.62],
            "score_ci_upper": [0.87, 0.78],
            "median_rank": [1.0, 2.0],
            "rank_ci_lower": [1.0, 1.0],
            "rank_ci_upper": [2.0, 2.0],
        }
    )
    pairwise = pd.DataFrame([[0.5, 0.8], [0.2, 0.5]], index=["A", "B"], columns=["A", "B"])
    tasks = pd.DataFrame({"disagreement": [0.0, 0.5, 1.0]})
    power = pd.DataFrame(
        {
            "n_tasks": [25, 100, 500],
            "power_mcnemar_exact": [0.2, 0.5, 0.9],
            "rank_reversal_probability": [0.25, 0.1, 0.02],
        }
    )

    paths = [
        plot_score_intervals(leaderboard, tmp_path / "score.png"),
        plot_rank_intervals(leaderboard, tmp_path / "rank.png"),
        plot_pairwise_ordering(pairwise, leaderboard, tmp_path / "pairwise.png"),
        plot_task_disagreement(tasks, tmp_path / "tasks.png"),
        plot_power_curve(power, tmp_path / "power.png"),
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
