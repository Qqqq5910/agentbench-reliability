from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
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


def _build_command(
    row: Mapping[str, object],
    system: Mapping[str, object],
    model: Mapping[str, object],
) -> str:
    adapter = system.get("adapter") or {}
    if not isinstance(adapter, dict):
        raise ValueError(f"adapter config missing for {row['system_id']}")
    kind = str(adapter.get("kind") or "")
    task_id = str(row["task_id"])
    run_id = str(row["run_id"])
    default_model_name = f"{model.get('provider')}/{model.get('model_id')}"
    model_name = str(model.get("litellm_model_name") or default_model_name)
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
                'python "$BENCHTRUST_REPO_ROOT/scripts/adapters/run_moatless_single.py"',
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
        required_secrets = (
            adapter.get("required_secrets") or [] if isinstance(adapter, dict) else []
        )
        checkout_dir = checkout_root / system_id
        rows.append(
            {
                **record,
                "checkout_dir": str(checkout_dir),
                "required_secrets": ",".join(str(value) for value in required_secrets),
                "result_dir": f"artifacts/stage2_pilot/runs/{_safe_run_dir(str(record['run_id']))}",
                "runtime_venv": f".benchtrust/stage2/venvs/{system_id}",
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
        required_paths = (
            adapter.get("required_paths") or [] if isinstance(adapter, dict) else []
        )
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


EXECUTION_PLAN_COLUMNS = {
    "execution_order",
    "run_id",
    "system_id",
    "task_id",
    "replicate_index",
    "checkout_dir",
    "required_secrets",
    "result_dir",
    "runtime_venv",
    "command",
}


def select_execution_rows(
    plan: pd.DataFrame,
    *,
    system_id: str | None = None,
    start_order: int = 1,
    limit: int | None = None,
) -> pd.DataFrame:
    """Select a deterministic contiguous pilot execution slice."""

    missing = EXECUTION_PLAN_COLUMNS - set(plan.columns)
    if missing:
        raise ValueError(f"pilot command plan missing columns: {sorted(missing)}")
    if start_order <= 0:
        raise ValueError("start_order must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when provided")

    selected = plan.loc[plan["execution_order"].astype(int) >= start_order].copy()
    if system_id is not None:
        selected = selected.loc[selected["system_id"].astype(str) == system_id].copy()
    selected = selected.sort_values("execution_order")
    if limit is not None:
        selected = selected.head(limit)
    if selected.empty:
        raise ValueError("pilot execution selection is empty")
    return selected.reset_index(drop=True)


def _required_secrets(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _classify_failure(stderr: str) -> str:
    normalized = stderr.lower()
    provider_markers = (
        "authentication",
        "api key",
        "rate limit",
        "ratelimit",
        "litellm",
        "openai",
        "provider",
    )
    infra_markers = (
        "docker daemon",
        "cannot connect to the docker",
        "no space left on device",
        "container runtime",
        "image pull",
    )
    if any(marker in normalized for marker in provider_markers):
        return "provider_error"
    if any(marker in normalized for marker in infra_markers):
        return "infra_error"
    return "harness_error"


def execute_pilot_plan(
    plan: pd.DataFrame,
    *,
    repo_root: Path = Path("."),
    status_output: Path = Path("artifacts/stage2_pilot/execution_status.csv"),
    system_id: str | None = None,
    start_order: int = 1,
    limit: int | None = None,
    execute: bool = False,
    redo: bool = False,
    timeout_seconds: int = 1800,
) -> pd.DataFrame:
    """Dry-run or execute a frozen pilot plan without inspecting solve performance."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    selected = select_execution_rows(
        plan,
        system_id=system_id,
        start_order=start_order,
        limit=limit,
    )
    root = repo_root.resolve()

    missing_secrets: dict[str, set[str]] = {}
    if execute:
        for row in selected.to_dict("records"):
            absent = {
                secret
                for secret in _required_secrets(row["required_secrets"])
                if not os.environ.get(secret)
            }
            if absent:
                missing_secrets.setdefault(str(row["system_id"]), set()).update(absent)
        if missing_secrets:
            details = "; ".join(
                f"{system}: {','.join(sorted(values))}"
                for system, values in sorted(missing_secrets.items())
            )
            raise ValueError(f"required pilot secrets are missing: {details}")

    status_rows: list[dict[str, object]] = []
    status_path = root / status_output
    status_path.parent.mkdir(parents=True, exist_ok=True)

    for row in selected.to_dict("records"):
        checkout = root / str(row["checkout_dir"])
        runtime_venv = root / str(row["runtime_venv"])
        result_dir = root / str(row["result_dir"])
        metadata_path = result_dir / "metadata.json"

        base_status = {
            "execution_order": int(row["execution_order"]),
            "run_id": str(row["run_id"]),
            "system_id": str(row["system_id"]),
            "task_id": str(row["task_id"]),
            "replicate_index": int(row["replicate_index"]),
            "command": str(row["command"]),
            "result_dir": str(row["result_dir"]),
        }

        if not execute:
            status_rows.append(
                {
                    **base_status,
                    "status": "dry_run",
                    "returncode": None,
                    "duration_seconds": 0.0,
                }
            )
            continue

        if not checkout.exists():
            raise ValueError(f"pilot checkout does not exist: {checkout}")
        if not runtime_venv.exists():
            raise ValueError(
                f"pilot runtime is not prepared: {runtime_venv}; "
                "run stage2-pilot-setup --install first"
            )

        if metadata_path.exists() and not redo:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing.get("status") == "completed":
                status_rows.append(
                    {
                        **base_status,
                        "status": "skipped_completed",
                        "returncode": existing.get("returncode"),
                        "duration_seconds": existing.get("duration_seconds"),
                    }
                )
                continue

        result_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["BENCHTRUST_REPO_ROOT"] = str(root)
        env["BENCHTRUST_RUN_DIR"] = str(result_dir)
        env["PATH"] = f"{runtime_venv / 'bin'}{os.pathsep}{env.get('PATH', '')}"

        started_at = datetime.now(UTC)
        started = time.monotonic()
        returncode: int | None = None
        stdout = ""
        stderr = ""
        try:
            completed = subprocess.run(
                str(row["command"]),
                cwd=checkout,
                env=env,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            status = "completed" if returncode == 0 else _classify_failure(stderr)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            status = "timeout"

        duration = time.monotonic() - started
        finished_at = datetime.now(UTC)
        (result_dir / "stdout.log").write_text(str(stdout), encoding="utf-8")
        (result_dir / "stderr.log").write_text(str(stderr), encoding="utf-8")

        metadata = {
            **base_status,
            "status": status,
            "returncode": returncode,
            "duration_seconds": duration,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "timeout_seconds": timeout_seconds,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        status_rows.append(metadata)
        pd.DataFrame(status_rows).to_csv(status_path, index=False)

    result = pd.DataFrame(status_rows)
    result.to_csv(status_path, index=False)
    return result


def build_runtime_plan(
    systems_config: Mapping[str, object],
    *,
    checkout_root: Path = Path("external/stage2"),
    venv_root: Path = Path(".benchtrust/stage2/venvs"),
) -> pd.DataFrame:
    """Build isolated runtime setup instructions for every candidate system."""

    systems = _systems_by_id(systems_config)
    rows: list[dict[str, object]] = []
    for system_id, system in systems.items():
        runtime = system.get("runtime") or {}
        if not isinstance(runtime, dict):
            raise ValueError(f"runtime config missing for {system_id}")
        install_target = str(runtime.get("install_target") or ".")
        smoke_command = str(runtime.get("smoke_command") or "").strip()
        if not smoke_command:
            raise ValueError(f"runtime smoke_command missing for {system_id}")
        rows.append(
            {
                "system_id": system_id,
                "repository": system.get("repository"),
                "commit": system.get("commit"),
                "checkout_dir": str(checkout_root / system_id),
                "venv_dir": str(venv_root / system_id),
                "install_target": install_target,
                "smoke_command": smoke_command,
            }
        )
    return pd.DataFrame(rows)


def setup_pilot_runtimes(
    runtime_plan: pd.DataFrame,
    *,
    repo_root: Path = Path("."),
    install: bool = False,
) -> pd.DataFrame:
    """Dry-run or create isolated candidate virtual environments without model calls."""

    required = {
        "system_id",
        "repository",
        "commit",
        "checkout_dir",
        "venv_dir",
        "install_target",
        "smoke_command",
    }
    missing = required - set(runtime_plan.columns)
    if missing:
        raise ValueError(f"runtime plan missing columns: {sorted(missing)}")

    root = repo_root.resolve()
    rows: list[dict[str, object]] = []
    for record in runtime_plan.to_dict("records"):
        system_id = str(record["system_id"])
        checkout = root / str(record["checkout_dir"])
        venv_dir = root / str(record["venv_dir"])
        base = {
            "system_id": system_id,
            "checkout_dir": str(record["checkout_dir"]),
            "venv_dir": str(record["venv_dir"]),
            "smoke_command": str(record["smoke_command"]),
        }
        if not install:
            rows.append({**base, "status": "dry_run", "returncode": None})
            continue

        if not checkout.exists():
            raise ValueError(f"candidate checkout does not exist: {checkout}")

        observed = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if observed != str(record["commit"]):
            raise ValueError(
                f"candidate checkout revision mismatch for {system_id}: "
                f"expected {record['commit']}, observed {observed}"
            )

        if not venv_dir.exists():
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
            )

        python_path = venv_dir / "bin" / "python"
        subprocess.run(
            [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            cwd=checkout,
        )
        install_target = str(record["install_target"])
        subprocess.run(
            [str(python_path), "-m", "pip", "install", "-e", install_target],
            check=True,
            cwd=checkout,
        )

        env = os.environ.copy()
        env["PATH"] = f"{venv_dir / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        smoke = subprocess.run(
            str(record["smoke_command"]),
            shell=True,
            executable="/bin/bash",
            cwd=checkout,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        rows.append(
            {
                **base,
                "status": "ready" if smoke.returncode == 0 else "smoke_failed",
                "returncode": smoke.returncode,
            }
        )

    return pd.DataFrame(rows)
