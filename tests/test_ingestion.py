import json
from pathlib import Path

import yaml

from benchtrust.ingestion.swebench import (
    catalog_submissions,
    load_submission_outcomes,
    reproduce_submission_scores,
)


def _write_submission(root: Path) -> Path:
    submission = root / "evaluation" / "verified" / "20260101_demo"
    (submission / "results").mkdir(parents=True)
    (submission / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "info": {"name": "Demo Agent", "resolved": 100.0 / 3.0},
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
    assert catalog.loc[0, "reported_score_percent"] == 100.0 / 3.0


def test_catalog_normalizes_historical_booleanish_metadata(tmp_path: Path) -> None:
    submission = _write_submission(tmp_path)
    metadata_path = submission / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    metadata["tags"]["checked"] = "false (See README.md for verification details)"
    metadata["tags"]["os_system"] = "true"
    metadata["tags"]["os_model"] = "unknown"
    metadata_path.write_text(yaml.safe_dump(metadata), encoding="utf-8")

    catalog = catalog_submissions(tmp_path)
    assert bool(catalog.loc[0, "checked"]) is False
    assert catalog.loc[0, "checked_raw"].startswith("false")
    assert bool(catalog.loc[0, "open_source_system"]) is True
    assert catalog.loc[0, "open_source_model"] is None
    assert catalog.loc[0, "open_source_model_raw"] == "unknown"


def test_load_submission_outcomes_expands_full_universe(tmp_path: Path) -> None:
    submission = _write_submission(tmp_path)
    outcomes = load_submission_outcomes(submission, ["task-1", "task-2", "task-3"])
    indexed = outcomes.set_index("task_id")
    assert indexed.loc["task-1", "resolved"] == 1
    assert indexed.loc["task-2", "status"] == "no_generation"
    assert indexed.loc["task-3", "status"] == "unresolved"
    assert indexed.loc["task-3", "resolved"] == 0


def test_reproduce_submission_scores_matches_independent_metadata(tmp_path: Path) -> None:
    submission = _write_submission(tmp_path)
    catalog = catalog_submissions(tmp_path)
    outcomes = load_submission_outcomes(submission, ["task-1", "task-2", "task-3"])
    result = reproduce_submission_scores(catalog, outcomes)
    assert result.loc[0, "reconstructed_resolved_count"] == 1
    assert result.loc[0, "resolved_count_matches"]
    assert result.loc[0, "reported_score_matches"]
    assert abs(result.loc[0, "score_difference_percent"]) < 1e-9
