import pandas as pd

from benchtrust.cohorts import select_single_attempt_cohort


def test_single_attempt_cohort_excludes_multi_attempt_and_failed_reproduction() -> None:
    catalog = pd.DataFrame(
        {
            "submission_id": ["single", "multi", "bad"],
            "attempts": [1, 5, 1],
        }
    )
    outcomes = pd.DataFrame(
        {
            "submission_id": ["single", "multi", "bad"],
            "task_id": ["t1", "t1", "t1"],
            "resolved": [1, 1, 0],
        }
    )
    reproduction = pd.DataFrame(
        {
            "submission_id": ["single", "multi", "bad"],
            "resolved_count_matches": [True, True, False],
            "reported_score_available": [True, False, True],
            "reported_score_matches": [True, False, True],
        }
    )

    selected_catalog, selected_outcomes = select_single_attempt_cohort(
        catalog, outcomes, reproduction
    )
    assert selected_catalog["submission_id"].tolist() == ["single"]
    assert selected_outcomes["submission_id"].tolist() == ["single"]
