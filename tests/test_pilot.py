from pathlib import Path

import pandas as pd

from benchtrust.pilot import (
    build_pilot_command_plan,
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
            },
            {
                "system_id": "mini",
                "scaffold": "mini-swe-agent",
                "repository": "org/mini",
                "commit": "b",
                "adapter": {"kind": "mini_swe_agent", "required_secrets": ["OPENAI_API_KEY"]},
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
