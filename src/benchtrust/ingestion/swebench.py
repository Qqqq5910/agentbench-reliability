from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def _load_results(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def catalog_submissions(
    experiments_root: str | Path,
    *,
    split: str = "verified",
) -> pd.DataFrame:
    """Catalog SWE-bench leaderboard entries from a local experiments checkout.

    The official experiments repository stores submission entries and pointers to
    artifacts. It does not imply that two entries with similar names are repeated
    independent runs of the same system, so every directory is retained as a distinct
    submission identity.
    """

    root = Path(experiments_root)
    evaluation_dir = root / "evaluation" / split
    if not evaluation_dir.is_dir():
        raise FileNotFoundError(f"missing SWE-bench evaluation directory: {evaluation_dir}")

    rows: list[dict[str, Any]] = []
    for submission_dir in sorted(path for path in evaluation_dir.iterdir() if path.is_dir()):
        metadata_path = submission_dir / "metadata.yaml"
        results_path = submission_dir / "results" / "results.json"
        if not metadata_path.is_file() or not results_path.is_file():
            continue

        metadata = _load_yaml(metadata_path)
        results = _load_results(results_path)
        info = metadata.get("info") or {}
        tags = metadata.get("tags") or {}
        system = tags.get("system") or {}
        models = tags.get("model") or []
        if isinstance(models, str):
            models = [models]
        assets = metadata.get("assets") or {}

        rows.append(
            {
                "submission_id": submission_dir.name,
                "benchmark": "swe-bench",
                "split": split,
                "display_name": info.get("name"),
                "agent": tags.get("agent"),
                "agent_org": tags.get("agent_org"),
                "model_ids": json.dumps(models, ensure_ascii=False),
                "model_display": tags.get("model_display"),
                "model_org": tags.get("model_org"),
                "attempts": system.get("attempts"),
                "checked": tags.get("checked"),
                "open_source_system": tags.get("os_system"),
                "open_source_model": tags.get("os_model"),
                "resolved_count": len(results.get("resolved") or []),
                "no_generation_count": len(results.get("no_generation") or []),
                "no_logs_count": len(results.get("no_logs") or []),
                "assets_json": json.dumps(assets, sort_keys=True, ensure_ascii=False),
                "metadata_path": metadata_path.as_posix(),
                "results_path": results_path.as_posix(),
            }
        )

    return pd.DataFrame(rows)


def load_submission_outcomes(
    submission_dir: str | Path,
    task_ids: Iterable[str],
) -> pd.DataFrame:
    """Expand one SWE-bench entry into a complete task-level binary outcome table.

    A trusted benchmark task universe must be supplied explicitly. Tasks listed as
    `resolved` receive outcome 1; all other benchmark tasks receive outcome 0, while
    preserving the more specific `no_generation` and `no_logs` status labels.
    """

    submission_path = Path(submission_dir)
    results_path = submission_path / "results" / "results.json"
    if not results_path.is_file():
        raise FileNotFoundError(f"missing results file: {results_path}")

    results = _load_results(results_path)
    categories = {
        "resolved": set(results.get("resolved") or []),
        "no_generation": set(results.get("no_generation") or []),
        "no_logs": set(results.get("no_logs") or []),
    }
    overlaps = (
        (categories["resolved"] & categories["no_generation"])
        | (categories["resolved"] & categories["no_logs"])
        | (categories["no_generation"] & categories["no_logs"])
    )
    if overlaps:
        raise ValueError(f"results categories overlap for {sorted(overlaps)[:5]}")

    universe = list(dict.fromkeys(str(task_id) for task_id in task_ids))
    if not universe:
        raise ValueError("task_ids must not be empty")
    universe_set = set(universe)
    reported = set().union(*categories.values())
    unknown = reported - universe_set
    if unknown:
        raise ValueError(
            "submission contains task IDs outside the provided benchmark universe: "
            f"{sorted(unknown)[:5]}"
        )

    rows: list[dict[str, Any]] = []
    submission_id = submission_path.name
    for task_id in universe:
        if task_id in categories["resolved"]:
            status = "resolved"
            resolved = 1
        elif task_id in categories["no_generation"]:
            status = "no_generation"
            resolved = 0
        elif task_id in categories["no_logs"]:
            status = "no_logs"
            resolved = 0
        else:
            status = "unresolved"
            resolved = 0
        rows.append(
            {
                "submission_id": submission_id,
                "system_id": submission_id,
                "task_id": task_id,
                "resolved": resolved,
                "status": status,
            }
        )

    return pd.DataFrame(rows)
