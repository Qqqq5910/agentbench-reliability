from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None
    return converted if converted >= 0 else None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    """Normalize historical boolean-ish metadata while preserving unknown states."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true" or normalized.startswith("true ") or normalized.startswith("true("):
            return True
        if normalized == "false" or normalized.startswith("false ") or normalized.startswith("false("):
            return False
    return None


def _raw_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


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

    Historical metadata are schema-drifted: fields such as ``checked`` and open-source
    flags can be booleans in some entries and explanatory strings in others. Typed
    normalized columns are emitted alongside ``*_raw`` text so Parquet schemas remain
    stable without discarding the original source value.
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
        attempts_raw = system.get("attempts")
        checked_raw = tags.get("checked")
        os_system_raw = tags.get("os_system")
        os_model_raw = tags.get("os_model")

        rows.append(
            {
                "submission_id": submission_dir.name,
                "benchmark": "swe-bench",
                "split": split,
                "display_name": info.get("name"),
                "reported_score_percent": _optional_float(info.get("resolved")),
                "agent": tags.get("agent"),
                "agent_org": tags.get("agent_org"),
                "model_ids": json.dumps(models, ensure_ascii=False),
                "model_display": tags.get("model_display"),
                "model_org": tags.get("model_org"),
                "attempts": _optional_int(attempts_raw),
                "attempts_raw": _raw_text(attempts_raw),
                "checked": _optional_bool(checked_raw),
                "checked_raw": _raw_text(checked_raw),
                "open_source_system": _optional_bool(os_system_raw),
                "open_source_system_raw": _raw_text(os_system_raw),
                "open_source_model": _optional_bool(os_model_raw),
                "open_source_model_raw": _raw_text(os_model_raw),
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


def reproduce_submission_scores(
    catalog: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    tolerance_percent: float = 1e-6,
) -> pd.DataFrame:
    """Recompute submission scores from task outcomes and compare official metadata.

    The reconstructed score is independent of `info.resolved` in metadata. A row is
    marked as matching only when an official reported score is present and its absolute
    difference from the reconstructed percentage is within `tolerance_percent`.
    """

    required_catalog = {"submission_id", "reported_score_percent", "resolved_count"}
    required_outcomes = {"submission_id", "task_id", "resolved"}
    missing_catalog = required_catalog - set(catalog.columns)
    missing_outcomes = required_outcomes - set(outcomes.columns)
    if missing_catalog:
        raise ValueError(f"catalog missing required columns: {sorted(missing_catalog)}")
    if missing_outcomes:
        raise ValueError(f"outcomes missing required columns: {sorted(missing_outcomes)}")
    if tolerance_percent < 0:
        raise ValueError("tolerance_percent must be non-negative")
    if outcomes.duplicated(["submission_id", "task_id"]).any():
        raise ValueError("outcomes contain duplicate submission-task pairs")
    non_missing = outcomes["resolved"].dropna()
    if not non_missing.isin([0, 1, False, True]).all():
        raise ValueError("resolved must contain only binary 0/1 values")

    grouped = (
        outcomes.groupby("submission_id", sort=False)["resolved"]
        .agg(reconstructed_resolved_count="sum", n_tasks="size")
        .reset_index()
    )
    grouped["reconstructed_score_percent"] = (
        100.0 * grouped["reconstructed_resolved_count"] / grouped["n_tasks"]
    )

    result = catalog.merge(grouped, on="submission_id", how="left", validate="one_to_one")
    result["resolved_count_matches"] = (
        result["resolved_count"] == result["reconstructed_resolved_count"]
    )
    reported = pd.to_numeric(result["reported_score_percent"], errors="coerce")
    result["score_difference_percent"] = result["reconstructed_score_percent"] - reported
    result["reported_score_available"] = reported.notna()
    result["reported_score_matches"] = result["reported_score_available"] & (
        result["score_difference_percent"].abs() <= tolerance_percent
    )
    return result
