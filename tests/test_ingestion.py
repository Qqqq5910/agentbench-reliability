import json
from pathlib import Path

import yaml

from benchtrust.ingestion.swebench import catalog_submissions, load_submission_outcomes


def _write_submission(root: Path) -> Path:
    submission = root / "evaluation" / "verified" / "20260101_demo"
    (submission / "results").mkdir(parents=True)
    (submission / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "info": {"name": "Demo Agent"},
                "assets": {"logs": "https://example.com/logs"},
                "tags": {
                    "agent": "Demo",
                    "agent_org": "Example",
                    "model": ["model-v1"],
                    "model_display": "Model V1",
                    "model_org": "Example",
                    "system": {"attempts": "1"},
                    "checked": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (submission / "results" / "results.json").write_text(
        json.dumps(
            {
                "resolved": ["task-1"],
                "no_generation": ["task-2"],
                "no_logs": [],
            }
        ),
        encoding="utf-8",
    )
    return submission


def test_catalog_submissions(tmp_path: Path) -> None:
    _write_submission(tmp_path)
    catalog = catalog_submissions(tmp_path)
    assert len(catalog) == 1
    assert catalog.loc[0, "submission_id"] == "20260101_demo"
    assert catalog.loc[0, "resolved_count"] == 1
    assert catalog.loc[0, "agent"] == "Demo"


def test_load_submission_outcomes_expands_full_universe(tmp_path: Path) -> None:
    submission = _write_submission(tmp_path)
    outcomes = load_submission_outcomes(submission, ["task-1", "task-2", "task-3"])
    indexed = outcomes.set_index("task_id")
    assert indexed.loc["task-1", "resolved"] == 1
    assert indexed.loc["task-2", "status"] == "no_generation"
    assert indexed.loc["task-3", "status"] == "unresolved"
    assert indexed.loc["task-3", "resolved"] == 0
