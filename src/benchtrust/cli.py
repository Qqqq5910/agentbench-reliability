from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

from .ingestion.swebench import catalog_submissions, load_submission_outcomes
from .power import paired_power_curve
from .statistics import bootstrap_leaderboard, task_summary
from .validation import validate_outcome_table

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
) -> None:
    """Run the Stage 1 bootstrap leaderboard and task-disagreement analysis."""

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
    typer.echo(f"Wrote analysis artifacts to {output_dir}")


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
    typer.echo(f"Wrote {output_path}")


@app.command("ingest-swebench")
def ingest_swebench(
    experiments_root: Path,
    task_universe: Path,
    output_dir: Path = Path("data/processed"),
    split: str = "verified",
) -> None:
    """Normalize an official SWE-bench experiments checkout into Parquet tables."""

    task_ids = _read_task_ids(task_universe)
    catalog = catalog_submissions(experiments_root, split=split)
    if catalog.empty:
        raise typer.BadParameter(f"no valid submissions found for split={split}")

    outcomes: list[pd.DataFrame] = []
    for submission_id in catalog["submission_id"]:
        submission_dir = experiments_root / "evaluation" / split / str(submission_id)
        outcomes.append(load_submission_outcomes(submission_dir, task_ids))

    output_dir.mkdir(parents=True, exist_ok=True)
    catalog.to_parquet(output_dir / f"swebench_{split}_submissions.parquet", index=False)
    pd.concat(outcomes, ignore_index=True).to_parquet(
        output_dir / f"swebench_{split}_outcomes.parquet",
        index=False,
    )
    typer.echo(
        f"Ingested {len(catalog)} submissions x {len(task_ids)} tasks into {output_dir}"
    )
