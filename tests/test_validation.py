import pandas as pd

from benchtrust.validation import validate_outcome_table


def test_validation_accepts_complete_binary_table() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A", "A", "B", "B"],
            "task_id": ["t1", "t2", "t1", "t2"],
            "resolved": [1, 0, 1, 1],
        }
    )
    report = validate_outcome_table(frame)
    assert report.ok
    assert report.complete_task_fraction == 1.0
    assert report.n_systems == 2
    assert report.n_tasks == 2


def test_validation_rejects_duplicate_pairs() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A", "A"],
            "task_id": ["t1", "t1"],
            "resolved": [1, 0],
        }
    )
    report = validate_outcome_table(frame)
    assert not report.ok
    assert any(issue.code == "duplicate_system_task" for issue in report.issues)


def test_validation_flags_incomplete_pairing() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["A", "A", "B"],
            "task_id": ["t1", "t2", "t1"],
            "resolved": [1, 0, 1],
        }
    )
    report = validate_outcome_table(frame)
    assert report.ok
    assert report.complete_task_fraction == 0.5
    assert any(issue.code == "incomplete_pairing" for issue in report.issues)
