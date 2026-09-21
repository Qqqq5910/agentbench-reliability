from pathlib import Path

import pandas as pd

from benchtrust.pilot import (
    build_pilot_command_plan,
    build_runtime_plan,
    execute_pilot_plan,
    setup_pilot_runtimes,
    select_execution_rows,
    validate_pilot_manifest,
)


def _config() -> dict:
    return {
        "common_model": {
            "provider": "openai",
            "model_id": "gpt-5.6-terra",
            "litellm_model_name": "openai/gpt-5.6-terra",
            "reasoning_effort": "medium",
        },
        "systems": [
            {
                "system_id": "swe",
                "scaffold": "SWE-agent",
                "repository": "org/swe",
                "commit": "a",
                "adapter": {"kind": "sweagent", "required_secrets": ["OPENAI_API_KEY"]},
                "runtime": {
                    "install_target": ".",
                    "smoke_command": "sweagent run-batch --help",
                },
            },
            {
                "system_id": "mini",
                "scaffold": "mini-swe-agent",
                "repository": "org/mini",
                "commit": "b",
                "adapter": {"kind": "mini_swe_agent", "required_secrets": ["OPENAI_API_KEY"]},
                "runtime": {
                    "install_target": ".",
                    "smoke_command": "mini-extra swebench-single --help",
                },
            },
            {
                "system_id": "moat",
                "scaffold": "Moatless",
                "repository": "org/moat",
                "commit": "c",
                "adapter": {
                    "kind": "moatless",
                    "required_secrets": ["OPENAI_API_KEY", "VOYAGE_API_KEY"],
                },
                "runtime": {
                    "install_target": ".",
                    "smoke_command": "python scripts/docker_run.py --help",
                },
            },
        ],
    }


def _manifest() -> pd.DataFrame:
    rows = []
    order = 1
    for system_id, scaffold, repo, commit in [
        ("swe", "SWE-agent", "org/swe", "a"),
        ("mini", "mini-swe-agent", "org/mini", "b"),
        ("moat", "Moatless", "org/moat", "c"),
    ]:
        for task_id in ["repo__1", "repo__2"]:
            for replicate in [1, 2]:
                rows.append(
                    {
                        "execution_order": order,
                        "run_id": f"pilot:{system_id}:{task_id}:r{replicate:02d}",
                        "phase": "pilot",
                        "system_id": system_id,
                        "scaffold": scaffold,
                        "scaffold_repository": repo,
                        "scaffold_commit": commit,
                        "model_provider": "openai",
                        "model_id": "gpt-5.6-terra",
                        "reasoning_effort": "medium",
                        "task_id": task_id,
                        "replicate_index": replicate,
                    }
                )
                order += 1
    return pd.DataFrame(rows)


def test_validate_manifest_and_build_commands() -> None:
    manifest = _manifest()
    config = _config()
    summary = validate_pilot_manifest(
        manifest, config, expected_tasks=2, expected_replicates=2
    )
    assert summary == {"rows": 12, "systems": 3, "tasks": 2, "replicates": 2}

    plan = build_pilot_command_plan(manifest, config, checkout_root=Path("external"))
    assert len(plan) == 12
    assert plan["command"].str.contains("gpt-5.6-terra").all()
    swe_commands = plan.loc[plan["system_id"] == "swe", "command"]
    assert swe_commands.str.contains("sweagent run-batch").all()
    mini_commands = plan.loc[plan["system_id"] == "mini", "command"]
    assert mini_commands.str.contains("mini-extra").all()
    moat_commands = plan.loc[plan["system_id"] == "moat", "command"]
    assert moat_commands.str.contains("run_moatless_single.py").all()


def test_manifest_rejects_wrong_model() -> None:
    manifest = _manifest()
    manifest.loc[0, "model_id"] = "other-model"
    try:
        validate_pilot_manifest(manifest, _config(), expected_tasks=2, expected_replicates=2)
    except ValueError as exc:
        assert "model_id" in str(exc)
    else:
        raise AssertionError("expected model mismatch to fail")


def _command_plan(tmp_path: Path) -> pd.DataFrame:
    manifest = _manifest()
    plan = build_pilot_command_plan(manifest, _config(), checkout_root=Path("external"))
    plan["result_dir"] = [
        str(Path("results") / f"run-{index}") for index in range(len(plan))
    ]
    return plan


def test_executor_dry_run_never_runs_commands(tmp_path: Path) -> None:
    plan = _command_plan(tmp_path)
    plan["command"] = "exit 99"
    result = execute_pilot_plan(
        plan,
        repo_root=tmp_path,
        status_output=Path("status.csv"),
        limit=3,
        execute=False,
    )
    assert len(result) == 3
    assert result["status"].eq("dry_run").all()
    assert (tmp_path / "status.csv").exists()


def test_executor_requires_secrets_before_execution(
    tmp_path: Path, monkeypatch
) -> None:
    plan = _command_plan(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        execute_pilot_plan(
            plan,
            repo_root=tmp_path,
            status_output=Path("status.csv"),
            limit=1,
            execute=True,
        )
    except ValueError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected missing secret validation to fail")


def test_select_execution_rows_respects_order_system_and_limit() -> None:
    plan = _command_plan(Path("."))
    selected = select_execution_rows(
        plan,
        system_id="mini",
        start_order=4,
        limit=2,
    )
    assert len(selected) == 2
    assert selected["system_id"].eq("mini").all()
    assert selected["execution_order"].min() >= 4


def test_runtime_setup_is_dry_run_by_default(tmp_path: Path) -> None:
    plan = build_runtime_plan(
        _config(),
        checkout_root=Path("external"),
        venv_root=Path("venvs"),
    )
    result = setup_pilot_runtimes(plan, repo_root=tmp_path, install=False)
    assert len(result) == 3
    assert result["status"].eq("dry_run").all()
    assert not (tmp_path / "venvs").exists()
