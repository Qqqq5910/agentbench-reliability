import pandas as pd

from benchtrust.power import paired_power_curve


def test_paired_power_curve_detects_large_difference() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A"] * 8 + ["B"] * 8,
            "task_id": [f"t{i}" for i in range(8)] * 2,
            "resolved": [1] * 8 + [0] * 8,
        }
    )
    result = paired_power_curve(frame, "A", "B", [25, 50], n_sim=500, seed=5)
    assert (result["power_mcnemar_exact"] > 0.99).all()
    assert (result["rank_reversal_probability"] == 0.0).all()
    assert (result["mean_score_difference"] == 1.0).all()


def test_power_simulation_is_reproducible() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A"] * 4 + ["B"] * 4,
            "task_id": ["t1", "t2", "t3", "t4"] * 2,
            "resolved": [1, 1, 0, 1, 1, 0, 0, 0],
        }
    )
    first = paired_power_curve(frame, "A", "B", [25], n_sim=500, seed=17)
    second = paired_power_curve(frame, "A", "B", [25], n_sim=500, seed=17)
    pd.testing.assert_frame_equal(first, second)
