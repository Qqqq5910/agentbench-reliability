from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import typer

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
from .power import paired_power_curve
from .provenance import build_manifest, write_manifest
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
