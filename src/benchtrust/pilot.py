from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pandas as pd


REQUIRED_MANIFEST_COLUMNS = {
    "execution_order",
    "run_id",
    "phase",
    "system_id",
    "scaffold",
    "scaffold_repository",
    "scaffold_commit",
    "model_provider",
    "model_id",
    "reasoning_effort",
    "task_id",
    "replicate_index",
}


def _systems_by_id(config: Mapping[str, object]) -> dict[str, dict]:
    systems = config.get("systems") or []
    result: dict[str, dict] = {}
    for raw in systems:
        if not isinstance(raw, dict):
            raise ValueError("systems entries must be mappings")
        system_id = str(raw.get("system_id") or "").strip()
        if not system_id:
            raise ValueError("every system requires system_id")
        if system_id in result:
            raise ValueError(f"duplicate system_id: {system_id}")
        result[system_id] = raw
    if not result:
        raise ValueError("systems config must contain at least one system")
    return result


def validate_pilot_manifest(
    manifest: pd.DataFrame,
    systems_config: Mapping[str, object],
    *,
    expected_tasks: int = 12,
    expected_replicates: int = 2,
) -> dict[str, int]:
    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)
    if missing:
        raise ValueError(f"pilot manifest missing columns: {sorted(missing)}")
    if manifest.empty:
        raise ValueError("pilot manifest must not be empty")
    if not manifest["phase"].eq("pilot").all():
        raise ValueError("pilot manifest contains non-pilot rows")
    if manifest["run_id"].duplicated().any():
        raise ValueError("pilot manifest contains duplicate run IDs")

    systems = _systems_by_id(systems_config)
    observed_systems = set(manifest["system_id"].astype(str))
    if observed_systems != set(systems):
        raise ValueError("pilot manifest system IDs do not match systems config")

    tasks = set(manifest["task_id"].astype(str))
    if len(tasks) != expected_tasks:
        raise ValueError(f"expected {expected_tasks} pilot tasks, found {len(tasks)}")

    grouped = manifest.groupby(["system_id", "task_id"], sort=False).size()
    if not grouped.eq(expected_replicates).all():
        raise ValueError("every system-task cell must have the frozen pilot replicate count")

    expected_rows = len(systems) * expected_tasks * expected_replicates
    if len(manifest) != expected_rows:
        raise ValueError(f"expected {expected_rows} pilot rows, found {len(manifest)}")

    order = manifest["execution_order"].astype(int).tolist()
    if sorted(order) != list(range(1, expected_rows + 1)):
        raise ValueError("execution_order must be a complete 1..N permutation")

    common = systems_config.get("common_model") or {}
    if not isinstance(common, dict):
        raise ValueError("common_model must be a mapping")
    expected_model = str(common.get("model_id") or "")
    expected_provider = str(common.get("provider") or "")
    expected_reasoning = str(common.get("reasoning_effort") or "")
    if not manifest["model_id"].astype(str).eq(expected_model).all():
        raise ValueError("manifest model_id does not match common_model")
    if not manifest["model_provider"].astype(str).eq(expected_provider).all():
        raise ValueError("manifest model_provider does not match common_model")
    if not manifest["reasoning_effort"].astype(str).eq(expected_reasoning).all():
        raise ValueError("manifest reasoning_effort does not match common_model")

    return {
        "rows": len(manifest),
        "systems": len(systems),
        "tasks": len(tasks),
        "replicates": expected_replicates,
    }


def _safe_run_dir(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", run_id)


def _build_command(row: Mapping[str, object], system: Mapping[str, object], model: Mapping[str, object]) -> str:
    adapter = system.get("adapter") or {}
    if not isinstance(adapter, dict):
        raise ValueError(f"adapter config missing for {row['system_id']}")
    kind = str(adapter.get("kind") or "")
    task_id = str(row["task_id"])
    run_id = str(row["run_id"])
    model_name = str(model.get("litellm_model_name") or f"{model.get('provider')}/{model.get('model_id')}")
    reasoning = str(model.get("reasoning_effort") or "medium")

    q_task = shlex.quote(f"^{re.escape(task_id)}$")
    q_model = shlex.quote(model_name)
    q_reasoning = shlex.quote(reasoning)
    q_run = shlex.quote(run_id)

    if kind == "sweagent":
        return " ".join(
            [
                "sweagent run-batch",
                "--config config/default.yaml",
                f"--agent.model.name {q_model}",
                f"--agent.model.completion_kwargs.reasoning_effort {q_reasoning}",
                "--agent.model.per_instance_cost_limit 0",
                "--agent.model.per_instance_call_limit 100",
                "--instances.type swe_bench",
                "--instances.subset verified",
                "--instances.split test",
                f"--instances.filter {q_task}",
                "--num_workers 1",
            ]
        )

    if kind == "mini_swe_agent":
        return " ".join(
            [
                "mini-extra swebench-single",
                "--subset verified",
                "--split test",
                f"--model {q_model}",
                f"--instance {shlex.quote(task_id)}",
                "--environment-class docker",
                "--exit-immediately",
                "-c swebench.yaml",
                f"-c model.model_kwargs.reasoning_effort={q_reasoning}",
            ]
        )

    if kind == "moatless":
        return " ".join(
            [
                "python ../../scripts/adapters/run_moatless_single.py",
                "--repo-dir .",
                f"--instance-id {shlex.quote(task_id)}",
                f"--model {q_model}",
                f"--reasoning-effort {q_reasoning}",
                f"--run-id {q_run}",
            ]
        )

    raise ValueError(f"unsupported pilot adapter kind: {kind}")


def build_pilot_command_plan(
    manifest: pd.DataFrame,
    systems_config: Mapping[str, object],
    *,
    checkout_root: Path = Path("external/stage2"),
) -> pd.DataFrame:
    systems = _systems_by_id(systems_config)
    model = systems_config.get("common_model") or {}
    if not isinstance(model, dict):
        raise ValueError("common_model must be a mapping")

    rows: list[dict[str, object]] = []
    for record in manifest.sort_values("execution_order").to_dict("records"):
        system_id = str(record["system_id"])
        system = systems[system_id]
        adapter = system.get("adapter") or {}
        required_secrets = adapter.get("required_secrets") or [] if isinstance(adapter, dict) else []
        checkout_dir = checkout_root / system_id
        rows.append(
            {
                **record,
                "checkout_dir": str(checkout_dir),
                "required_secrets": ",".join(str(value) for value in required_secrets),
                "result_dir": f"artifacts/stage2_pilot/runs/{_safe_run_dir(str(record['run_id']))}",
                "command": _build_command(record, system, model),
            }
        )
    return pd.DataFrame(rows)


def verify_pinned_checkouts(
    systems_config: Mapping[str, object],
    *,
    checkout_root: Path = Path("external/stage2"),
) -> pd.DataFrame:
    systems = _systems_by_id(systems_config)
    rows: list[dict[str, object]] = []
    for system_id, system in systems.items():
        checkout = checkout_root / system_id
        expected_commit = str(system.get("commit") or "")
        adapter = system.get("adapter") or {}
        required_paths = adapter.get("required_paths") or [] if isinstance(adapter, dict) else []
        observed_commit = None
        errors: list[str] = []
        if not checkout.exists():
            errors.append("checkout_missing")
        else:
            try:
                completed = subprocess.run(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                observed_commit = completed.stdout.strip()
            except (FileNotFoundError, subprocess.CalledProcessError):
                errors.append("git_revision_unavailable")
            if observed_commit and observed_commit != expected_commit:
                errors.append("commit_mismatch")
            for relative_path in required_paths:
                if not (checkout / str(relative_path)).exists():
                    errors.append(f"missing_path:{relative_path}")
        rows.append(
            {
                "system_id": system_id,
                "repository": system.get("repository"),
                "expected_commit": expected_commit,
                "observed_commit": observed_commit,
                "ok": not errors,
                "errors": ";".join(errors),
            }
        )
    return pd.DataFrame(rows)
