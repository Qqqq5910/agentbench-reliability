from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _save(fig: plt.Figure, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_score_intervals(
    leaderboard: pd.DataFrame,
    output_path: str | Path,
    *,
    system_col: str = "system_id",
    top_n: int = 20,
) -> Path:
    """Plot point estimates and bootstrap confidence intervals for top systems."""

    required = {system_col, "score", "score_ci_lower", "score_ci_upper"}
    missing = required - set(leaderboard.columns)
    if missing:
        raise ValueError(f"leaderboard missing required columns: {sorted(missing)}")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    frame = leaderboard.nlargest(min(top_n, len(leaderboard)), "score").sort_values("score")
    y = np.arange(len(frame))
    score = frame["score"].to_numpy(dtype=float)
    lower = frame["score_ci_lower"].to_numpy(dtype=float)
    upper = frame["score_ci_upper"].to_numpy(dtype=float)
    xerr = np.vstack([score - lower, upper - score])

    fig, ax = plt.subplots(figsize=(9, max(4.5, 0.34 * len(frame) + 1.5)))
    ax.errorbar(score, y, xerr=xerr, fmt="o", capsize=3)
    ax.set_yticks(y, frame[system_col].astype(str))
    ax.set_xlabel("Resolved fraction")
    ax.set_title("Leaderboard scores with task-bootstrap 95% intervals")
    ax.grid(axis="x", alpha=0.25)
    return _save(fig, output_path)


def plot_rank_intervals(
    leaderboard: pd.DataFrame,
    output_path: str | Path,
    *,
    system_col: str = "system_id",
    top_n: int = 20,
) -> Path:
    """Plot median bootstrap ranks and percentile rank intervals."""

    required = {system_col, "score", "median_rank", "rank_ci_lower", "rank_ci_upper"}
    missing = required - set(leaderboard.columns)
    if missing:
        raise ValueError(f"leaderboard missing required columns: {sorted(missing)}")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    frame = leaderboard.nlargest(min(top_n, len(leaderboard)), "score").copy()
    frame = frame.sort_values("median_rank", ascending=False)
    y = np.arange(len(frame))
    rank = frame["median_rank"].to_numpy(dtype=float)
    lower = frame["rank_ci_lower"].to_numpy(dtype=float)
    upper = frame["rank_ci_upper"].to_numpy(dtype=float)
    xerr = np.vstack([rank - lower, upper - rank])

    fig, ax = plt.subplots(figsize=(9, max(4.5, 0.34 * len(frame) + 1.5)))
    ax.errorbar(rank, y, xerr=xerr, fmt="o", capsize=3)
    ax.set_yticks(y, frame[system_col].astype(str))
    ax.set_xlabel("Bootstrap rank (lower is better)")
    ax.set_title("Rank uncertainty under task resampling")
    ax.grid(axis="x", alpha=0.25)
    ax.invert_xaxis()
    return _save(fig, output_path)


def plot_pairwise_ordering(
    pairwise: pd.DataFrame,
    leaderboard: pd.DataFrame,
    output_path: str | Path,
    *,
    system_col: str = "system_id",
    top_n: int = 20,
) -> Path:
    """Plot pairwise bootstrap ordering frequencies for the leading systems."""

    if system_col not in leaderboard.columns or "score" not in leaderboard.columns:
        raise ValueError("leaderboard must contain system_id and score columns")
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    systems = (
        leaderboard.nlargest(min(top_n, len(leaderboard)), "score")[system_col]
        .astype(str)
        .tolist()
    )
    missing = [system for system in systems if system not in pairwise.index or system not in pairwise]
    if missing:
        raise ValueError(f"pairwise matrix missing systems: {missing[:5]}")
    matrix = pairwise.loc[systems, systems].to_numpy(dtype=float)

    fig_size = max(7.0, 0.45 * len(systems) + 2.5)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    image = ax.imshow(matrix, vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(np.arange(len(systems)), systems, rotation=90)
    ax.set_yticks(np.arange(len(systems)), systems)
    ax.set_xlabel("System B")
    ax.set_ylabel("System A")
    ax.set_title("Bootstrap frequency that A ranks above B (ties split 0.5)")
    fig.colorbar(image, ax=ax, label="Ordering frequency")
    return _save(fig, output_path)


def plot_task_disagreement(task_frame: pd.DataFrame, output_path: str | Path) -> Path:
    """Plot the distribution of cross-system task disagreement."""

    if "disagreement" not in task_frame.columns:
        raise ValueError("task summary missing disagreement column")
    values = task_frame["disagreement"].dropna().to_numpy(dtype=float)
    if values.size == 0:
        raise ValueError("task summary has no disagreement values")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(values, bins=np.linspace(0.0, 1.0, 21), edgecolor="white")
    ax.set_xlabel("Normalized disagreement, 4p(1-p)")
    ax.set_ylabel("Tasks")
    ax.set_title("Cross-system disagreement across benchmark tasks")
    ax.grid(axis="y", alpha=0.2)
    return _save(fig, output_path)


def plot_power_curve(power_frame: pd.DataFrame, output_path: str | Path) -> Path:
    """Plot benchmark size against paired exact-test detection power."""

    required = {"n_tasks", "power_mcnemar_exact", "rank_reversal_probability"}
    missing = required - set(power_frame.columns)
    if missing:
        raise ValueError(f"power table missing required columns: {sorted(missing)}")
    frame = power_frame.sort_values("n_tasks")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(frame["n_tasks"], frame["power_mcnemar_exact"], marker="o", label="Detection power")
    ax.plot(
        frame["n_tasks"],
        frame["rank_reversal_probability"],
        marker="o",
        label="Rank reversal probability",
    )
    ax.axhline(0.8, linestyle="--", linewidth=1, label="80% power")
    ax.set_xscale("log")
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Number of benchmark tasks")
    ax.set_ylabel("Probability")
    ax.set_title("Benchmark-size sensitivity for a paired system comparison")
    ax.grid(alpha=0.2)
    ax.legend()
    return _save(fig, output_path)
