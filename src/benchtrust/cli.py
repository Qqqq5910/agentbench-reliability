from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import typer
import yaml

from .cohorts import select_single_attempt_cohort
from .ingestion.huggingface import (
    SWE_BENCH_VERIFIED_REPO,
    SWE_BENCH_VERIFIED_REVISION,
    SWE_BENCH_VERIFIED_SHA256,
    fetch_swebench_verified_task_universe,
)
from .ingestion.swebench import (
    catalog_submissions,
    load_submission_outcomes,
    reproduce_submission_scores,
)
from .pilot import build_pilot_command_plan, validate_pilot_manifest, verify_pinned_checkouts
from .power import paired_power_curve
from .provenance import build_manifest, write_manifest
from .stage2 import (
    build_execution_manifest,
    recommend_replicates,
    select_pilot_tasks,
    select_stage2_tasks,
    simulate_replicate_design,
)
from .statistics import bootstrap_leaderboard, task_summary
from .validation import validate_outcome_table
from .visualization import (
    plot_pairwise_ordering,
    plot_power_curve,
    plot_rank_intervals,
    plot_score_intervals,
    plot_task_disagreement,
)

app = typer.Typer(no_args_is_help=True, help="Reliability analysis for AI benchmarks.")


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise typer.BadParameter("input must be CSV or Parquet")


def _read_task_ids(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        if "task_id" not in frame.columns:
            raise typer.BadParameter("task universe CSV must contain a task_id column")
        values = frame["task_id"].dropna().astype(str).tolist()
    else:
        values = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return list(dict.fromkeys(values))


def _git_head(repo_path: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise typer.BadParameter(
            f"{repo_path} must be a Git checkout with git available"
        ) from exc
    return completed.stdout.strip()


@app.command()
def validate(input_path: Path) -> None:
    """Validate a tidy system-task outcome table."""

    frame = _read_table(input_path)
    report = validate_outcome_table(frame)
    payload = {
        "ok": report.ok,
        "n_rows": report.n_rows,
        "n_systems": report.n_systems,
        "n_tasks": report.n_tasks,
        "complete_task_fraction": report.complete_task_fraction,
        "issues": [issue.__dict__ for issue in report.issues],
    }
    typer.echo(json.dumps(payload, indent=2))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def analyze(
    input_path: Path,
    output_dir: Path = Path("artifacts/analysis"),
    n_boot: int = 10_000,
    seed: int = 0,
    top_n_figures: int = 20,
) -> None:
    """Run Stage 1 bootstrap analyses and generate core figures."""

    frame = _read_table(input_path)
    report = validate_outcome_table(frame)
    if not report.ok:
        for issue in report.issues:
            typer.echo(f"{issue.severity}: {issue.code}: {issue.message}", err=True)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    leaderboard, pairwise = bootstrap_leaderboard(frame, n_boot=n_boot, seed=seed)
    tasks = task_summary(frame)
    leaderboard.to_csv(output_dir / "leaderboard_bootstrap.csv", index=False)
    pairwise.to_csv(output_dir / "pairwise_ordering_probability.csv")
    tasks.to_csv(output_dir / "task_summary.csv", index=False)

    figure_dir = output_dir / "figures"
    plot_score_intervals(
        leaderboard, figure_dir / "fig01_score_intervals.png", top_n=top_n_figures
    )
    plot_rank_intervals(
        leaderboard, figure_dir / "fig02_rank_intervals.png", top_n=top_n_figures
    )
    plot_pairwise_ordering(
        pairwise,
        leaderboard,
        figure_dir / "fig03_pairwise_ordering.png",
        top_n=top_n_figures,
    )
    plot_task_disagreement(tasks, figure_dir / "fig04_task_disagreement.png")
    typer.echo(f"Wrote analysis tables and figures to {output_dir}")


@app.command()
def power(
    input_path: Path,
    system_a: str,
    system_b: str,
    output_path: Path = Path("artifacts/analysis/power_curve.csv"),
    sample_sizes: str = "25,50,100,200,500,1000",
    n_sim: int = 5_000,
    seed: int = 0,
) -> None:
    """Estimate paired benchmark-size sensitivity for two systems."""

    frame = _read_table(input_path)
    sizes = [int(value.strip()) for value in sample_sizes.split(",") if value.strip()]
    result = paired_power_curve(
        frame,
        system_a,
        system_b,
        sizes,
        n_sim=n_sim,
        seed=seed,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    figure_path = output_path.with_suffix(".png")
    plot_power_curve(result, figure_path)
    typer.echo(f"Wrote {output_path} and {figure_path}")


@app.command("stage2-design")
def stage2_design(
    task_summary_path: Path = Path("artifacts/stage1/task_summary.csv"),
    config_path: Path = Path("configs/stage2.yaml"),
    systems_config_path: Path = Path("configs/stage2_systems.yaml"),
    task_output: Path = Path("data/stage2/task_subset.csv"),
    pilot_output: Path = Path("data/stage2/pilot_task_subset.csv"),
    pilot_manifest_output: Path = Path("data/stage2/pilot_run_manifest.csv"),
    artifact_dir: Path = Path("artifacts/stage2_design"),
) -> None:
    """Freeze the Stage 2 task subset and simulate the required replicate count."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    systems_config = yaml.safe_load(
        systems_config_path.read_text(encoding="utf-8")
    ) or {}
    task_config = config.get("task_selection") or {}
    replicate_config = config.get("replicate_design") or {}
    pilot_config = config.get("pilot_selection") or {}
    seed = int(config.get("seed", 20260921))

    task_frame = _read_table(task_summary_path)
    selected = select_stage2_tasks(
        task_frame,
        total_tasks=int(task_config["total_tasks"]),
        representative_tasks=int(task_config["representative_tasks"]),
        enriched_tasks=int(task_config["enriched_tasks"]),
        disagreement_threshold=float(task_config["disagreement_threshold"]),
        seed=seed,
    )

    pilot_seed = int(pilot_config.get("seed", seed + 1))
    pilot = select_pilot_tasks(
        task_frame,
        selected,
        n_tasks=int(pilot_config.get("n_tasks", 12)),
        seed=pilot_seed,
    )

    execution_seed = int(pilot_config.get("execution_order_seed", pilot_seed + 1))
    pilot_manifest = build_execution_manifest(
        pilot,
        systems_config.get("systems") or [],
        replicates=int(pilot_config.get("replicates", 2)),
        seed=execution_seed,
        phase="pilot",
        common_model=systems_config.get("common_model") or {},
    )

    scenario_config = replicate_config.get("scenarios") or {}
    scenarios = {
        str(name): float(values["temperature"])
        for name, values in scenario_config.items()
    }
    simulation = simulate_replicate_design(
        selected,
        candidate_replicates=[int(value) for value in replicate_config["candidates"]],
        scenarios=scenarios,
        target_rate_a=float(replicate_config["target_rate_a"]),
        target_rate_b=float(replicate_config["target_rate_b"]),
        n_sim=int(replicate_config["n_sim"]),
        seed=seed,
    )
    thresholds = {
        str(key): float(value)
        for key, value in (replicate_config.get("thresholds") or {}).items()
    }
    primary_scenario = str(replicate_config["primary_scenario"])
    recommendation, simulation = recommend_replicates(
        simulation,
        primary_scenario=primary_scenario,
        thresholds=thresholds,
    )

    task_output.parent.mkdir(parents=True, exist_ok=True)
    pilot_output.parent.mkdir(parents=True, exist_ok=True)
    pilot_manifest_output.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    selected.to_csv(task_output, index=False)
    pilot.to_csv(pilot_output, index=False)
    pilot_manifest.to_csv(pilot_manifest_output, index=False)
    simulation.to_csv(artifact_dir / "replicate_design.csv", index=False)

    component_counts = selected["selection_component"].value_counts()
    high_disagreement_count = int(
        (selected["disagreement"] >= float(task_config["disagreement_threshold"])).sum()
    )
    recommendation_text = (
        "not reached by candidates"
        if recommendation is None
        else str(recommendation)
    )
    primary_rows = simulation.loc[simulation["scenario"] == primary_scenario].copy()

    lines = [
        "# Stage 2 design snapshot",
        "",
        f"- Frozen task subset: **{len(selected)}** tasks.",
        (
            "- Representative component: "
            f"**{int(component_counts.get('representative', 0))}** tasks."
        ),
        (
            "- High-disagreement enrichment: "
            f"**{int(component_counts.get('high_disagreement_enrichment', 0))}** tasks."
        ),
        (
            "- Selected tasks with Stage 1 disagreement at or above the enrichment "
            f"threshold: **{high_disagreement_count}/{len(selected)}**."
        ),
        f"- Selection seed: **{seed}**.",
        f"- Pilot tasks excluded from confirmatory analysis: **{len(pilot)}**.",
        f"- Pilot selection seed: **{pilot_seed}**.",
        f"- Pilot planned executions: **{len(pilot_manifest)}**.",
        f"- Pilot execution-order seed: **{execution_seed}**.",
        f"- Primary replicate-design scenario: **{primary_scenario}**.",
        f"- Recommended replicate count: **{recommendation_text}**.",
        "",
        "## Primary-scenario precision table",
        "",
        "| replicates | score p95 abs error | run-SD median rel. error | "
        "paired-diff CI half-width | unstable detection | rank-reversal abs error | meets gate |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in primary_rows.itertuples(index=False):
        lines.append(
            f"| {int(row.replicates)} | {row.score_abs_error_p95:.3f} | "
            f"{row.run_sd_median_relative_error:.3f} | "
            f"{row.paired_diff_ci_median_halfwidth:.3f} | "
            f"{row.unstable_detection_mean:.3f} | "
            f"{row.rank_reversal_median_abs_error:.3f} | "
            f"{'yes' if bool(row.meets_primary_precision) else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This is a design simulation, not evidence of observed within-system rerun "
            "stochasticity. Stage 1 cross-system solve rates are used only to preserve a "
            "realistic task-difficulty shape. Actual run-to-run stochasticity will be "
            "estimated only after controlled Stage 2 repetitions are collected.",
            "",
        ]
    )
    (artifact_dir / "DESIGN_SNAPSHOT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    typer.echo(
        f"Wrote {task_output}, {pilot_output}, {pilot_manifest_output}, and design "
        f"artifacts to {artifact_dir}; recommended_replicates={recommendation_text}"
    )


@app.command("stage2-pilot-plan")
def stage2_pilot_plan(
    manifest_path: Path = Path("data/stage2/pilot_run_manifest.csv"),
    pilot_tasks_path: Path = Path("data/stage2/pilot_task_subset.csv"),
    stage2_config_path: Path = Path("configs/stage2.yaml"),
    systems_config_path: Path = Path("configs/stage2_systems.yaml"),
    output_path: Path = Path("data/stage2/pilot_command_plan.csv"),
    snapshot_path: Path = Path("artifacts/stage2_pilot/PREFLIGHT.md"),
    checkout_root: Path = Path("external/stage2"),
    verify_checkouts: bool = False,
    refresh_manifest: bool = True,
) -> None:
    """Validate the frozen pilot matrix and generate auditable scaffold commands."""

    systems_config = yaml.safe_load(
        systems_config_path.read_text(encoding="utf-8")
    ) or {}
    stage2_config = yaml.safe_load(
        stage2_config_path.read_text(encoding="utf-8")
    ) or {}

    if refresh_manifest:
        pilot_tasks = _read_table(pilot_tasks_path)
        pilot_config = stage2_config.get("pilot_selection") or {}
        pilot_seed = int(pilot_config.get("execution_order_seed", 20260923))
        manifest = build_execution_manifest(
            pilot_tasks,
            systems_config.get("systems") or [],
            replicates=int(pilot_config.get("replicates", 2)),
            seed=pilot_seed,
            phase="pilot",
            common_model=systems_config.get("common_model") or {},
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest.to_csv(manifest_path, index=False)
    else:
        manifest = _read_table(manifest_path)

    summary = validate_pilot_manifest(manifest, systems_config)
    plan = build_pilot_command_plan(
        manifest, systems_config, checkout_root=checkout_root
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plan.to_csv(output_path, index=False)

    verification = None
    if verify_checkouts:
        verification = verify_pinned_checkouts(
            systems_config, checkout_root=checkout_root
        )
        if not verification["ok"].all():
            typer.echo(verification.to_string(index=False), err=True)
            raise typer.Exit(code=1)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    systems = systems_config.get("systems") or []
    lines = [
        "# Stage 2 pilot preflight",
        "",
        f"- Planned pilot executions: **{summary['rows']}**.",
        f"- Candidate systems: **{summary['systems']}**.",
        f"- Pilot tasks: **{summary['tasks']}**.",
        f"- Replicates per system-task cell: **{summary['replicates']}**.",
        "- Paid model calls executed by this command: **0**.",
        "",
        "## Candidates",
        "",
    ]
    for system in systems:
        adapter = system.get("adapter") or {}
        lines.append(
            f"- `{system['system_id']}`: `{system['repository']}@{system['commit']}` "
            f"via `{adapter.get('kind')}`."
        )
    if verification is not None:
        lines.extend(["", "## Checkout verification", ""])
        for row in verification.itertuples(index=False):
            lines.append(
                f"- `{row.system_id}`: {'PASS' if row.ok else 'FAIL'} "
                f"({row.observed_commit or 'no revision'})"
            )
    lines.extend(
        [
            "",
            "This is a no-model-call preflight. Pilot solve outcomes are not generated "
            "or inspected.",
            "",
        ]
    )
    snapshot_path.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(f"Wrote {output_path} and {snapshot_path}")


@app.command("fetch-swebench-verified")
def fetch_swebench_verified(
    output_dir: Path = Path("data/raw/swebench_verified"),
) -> None:
    """Fetch the pinned official 500-task SWE-bench Verified universe."""

    parquet_path, task_path = fetch_swebench_verified_task_universe(output_dir)
    manifest = build_manifest(
        benchmark="swe-bench",
        benchmark_split="verified",
        sources=[
            {
                "name": "SWE-bench Verified dataset",
                "url": f"https://huggingface.co/datasets/{SWE_BENCH_VERIFIED_REPO}",
                "revision": SWE_BENCH_VERIFIED_REVISION,
                "parquet_sha256": SWE_BENCH_VERIFIED_SHA256,
            }
        ],
        files=[parquet_path, task_path],
        extra={"expected_task_count": 500},
    )
    manifest_path = write_manifest(manifest, output_dir / "provenance.json")
    typer.echo(f"Wrote pinned task universe and {manifest_path}")


@app.command("ingest-swebench")
def ingest_swebench(
    experiments_root: Path,
    task_universe: Path,
    experiments_revision: str = typer.Option(
        ...,
        "--experiments-revision",
        help="Exact SWE-bench/experiments Git commit SHA expected in the local checkout.",
    ),
    output_dir: Path = Path("data/processed"),
    split: str = "verified",
) -> None:
    """Normalize a pinned SWE-bench experiments checkout into Parquet tables."""

    actual_revision = _git_head(experiments_root)
    if actual_revision != experiments_revision:
        raise typer.BadParameter(
            "experiments checkout revision mismatch: "
            f"expected {experiments_revision}, observed {actual_revision}"
        )

    task_ids = _read_task_ids(task_universe)
    catalog = catalog_submissions(experiments_root, split=split)
    if catalog.empty:
        raise typer.BadParameter(f"no valid submissions found for split={split}")

    outcomes_list: list[pd.DataFrame] = []
    for submission_id in catalog["submission_id"]:
        submission_dir = experiments_root / "evaluation" / split / str(submission_id)
        outcomes_list.append(load_submission_outcomes(submission_dir, task_ids))
    outcomes = pd.concat(outcomes_list, ignore_index=True)
    reproduction = reproduce_submission_scores(catalog, outcomes)
    primary_catalog, primary_outcomes = select_single_attempt_cohort(
        catalog, outcomes, reproduction
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / f"swebench_{split}_submissions.parquet"
    outcomes_path = output_dir / f"swebench_{split}_outcomes.parquet"
    reproduction_path = output_dir / f"swebench_{split}_score_reproduction.csv"
    primary_catalog_path = output_dir / f"swebench_{split}_primary_submissions.parquet"
    primary_outcomes_path = output_dir / f"swebench_{split}_primary_outcomes.parquet"
    catalog.to_parquet(catalog_path, index=False)
    outcomes.to_parquet(outcomes_path, index=False)
    reproduction.to_csv(reproduction_path, index=False)
    primary_catalog.to_parquet(primary_catalog_path, index=False)
    primary_outcomes.to_parquet(primary_outcomes_path, index=False)

    manifest = build_manifest(
        benchmark="swe-bench",
        benchmark_split=split,
        sources=[
            {
                "name": "SWE-bench experiments",
                "url": "https://github.com/SWE-bench/experiments",
                "revision": experiments_revision,
            }
        ],
        files=[
            task_universe,
            catalog_path,
            outcomes_path,
            reproduction_path,
            primary_catalog_path,
            primary_outcomes_path,
        ],
        extra={
            "submission_count": len(catalog),
            "primary_single_attempt_submission_count": len(primary_catalog),
            "task_count": len(task_ids),
            "outcome_rows": len(outcomes),
            "primary_outcome_rows": len(primary_outcomes),
        },
    )
    manifest_path = write_manifest(
        manifest, output_dir / f"swebench_{split}_provenance.json"
    )

    count_failures = int((~reproduction["resolved_count_matches"]).sum())
    reported_rows = reproduction[reproduction["reported_score_available"]]
    score_failures = int((~reported_rows["reported_score_matches"]).sum())
    typer.echo(
        f"Ingested {len(catalog)} submissions x {len(task_ids)} tasks into {output_dir}; "
        f"primary single-attempt submissions={len(primary_catalog)}; "
        f"score reproduction failures={score_failures}, count failures={count_failures}; "
        f"manifest={manifest_path}"
    )
    if count_failures or score_failures:
        raise typer.Exit(code=1)
