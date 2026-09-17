from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import rankdata


@dataclass(frozen=True)
class IntervalEstimate:
    """Point estimate plus a percentile bootstrap confidence interval."""

    estimate: float
    lower: float
    upper: float
    level: float
    n: int


def _as_binary_array(
    values: pd.Series | np.ndarray | list[int] | tuple[int, ...],
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("outcomes must be one-dimensional")
    if arr.size == 0:
        raise ValueError("outcomes must not be empty")
    if np.isnan(arr).any():
        raise ValueError("outcomes must not contain missing values")
    unique = np.unique(arr)
    if not np.isin(unique, [0.0, 1.0]).all():
        raise ValueError("outcomes must contain only 0/1 values")
    return arr


def _quantile_bounds(samples: np.ndarray, level: float) -> tuple[float, float]:
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    alpha = (1.0 - level) / 2.0
    lower, upper = np.quantile(samples, [alpha, 1.0 - alpha])
    return float(lower), float(upper)


def score_interval(
    outcomes: pd.Series | np.ndarray | list[int] | tuple[int, ...],
    *,
    n_boot: int = 10_000,
    level: float = 0.95,
    seed: int | None = 0,
) -> IntervalEstimate:
    """Estimate a binary benchmark score and task-bootstrap confidence interval."""

    arr = _as_binary_array(outcomes)
    if n_boot < 100:
        raise ValueError("n_boot must be at least 100")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, arr.size, size=(n_boot, arr.size))
    samples = arr[indices].mean(axis=1)
    lower, upper = _quantile_bounds(samples, level)
    return IntervalEstimate(float(arr.mean()), lower, upper, level, int(arr.size))


def paired_difference_interval(
    outcomes_a: pd.Series | np.ndarray | list[int] | tuple[int, ...],
    outcomes_b: pd.Series | np.ndarray | list[int] | tuple[int, ...],
    *,
    n_boot: int = 10_000,
    level: float = 0.95,
    seed: int | None = 0,
) -> IntervalEstimate:
    """Bootstrap the paired score difference A - B while preserving task pairing."""

    a = _as_binary_array(outcomes_a)
    b = _as_binary_array(outcomes_b)
    if a.size != b.size:
        raise ValueError("paired outcomes must have the same length")
    if n_boot < 100:
        raise ValueError("n_boot must be at least 100")
    diff = a - b
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, diff.size, size=(n_boot, diff.size))
    samples = diff[indices].mean(axis=1)
    lower, upper = _quantile_bounds(samples, level)
    return IntervalEstimate(float(diff.mean()), lower, upper, level, int(diff.size))


def _complete_task_matrix(
    frame: pd.DataFrame,
    *,
    system_col: str,
    task_col: str,
    outcome_col: str,
) -> pd.DataFrame:
    required = {system_col, task_col, outcome_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.duplicated([system_col, task_col], keep=False).any():
        raise ValueError("expected at most one outcome per system-task pair")
    non_missing = frame[outcome_col].dropna().to_numpy()
    _as_binary_array(non_missing)
    pivot = frame.pivot(index=task_col, columns=system_col, values=outcome_col)
    pivot = pivot.dropna(axis=0, how="any")
    if pivot.empty:
        raise ValueError("no complete tasks remain after aligning systems")
    return pivot.astype(float).sort_index(axis=1)


def bootstrap_leaderboard(
    frame: pd.DataFrame,
    *,
    system_col: str = "system_id",
    task_col: str = "task_id",
    outcome_col: str = "resolved",
    n_boot: int = 10_000,
    level: float = 0.95,
    seed: int | None = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate score intervals, rank intervals, and pairwise ordering stability.

    Only tasks observed for every included system are used. Resampling occurs at the
    task level, so the paired outcome structure is retained across systems.
    """

    if n_boot < 100:
        raise ValueError("n_boot must be at least 100")
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    matrix = _complete_task_matrix(
        frame,
        system_col=system_col,
        task_col=task_col,
        outcome_col=outcome_col,
    )
    arr = matrix.to_numpy(dtype=float)
    systems = matrix.columns.to_list()
    n_tasks, n_systems = arr.shape
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n_tasks, size=(n_boot, n_tasks))
    bootstrap_scores = arr[indices, :].mean(axis=1)

    alpha = (1.0 - level) / 2.0
    lower = np.quantile(bootstrap_scores, alpha, axis=0)
    upper = np.quantile(bootstrap_scores, 1.0 - alpha, axis=0)
    ranks = np.vstack([rankdata(-row, method="average") for row in bootstrap_scores])
    rank_lower = np.quantile(ranks, alpha, axis=0)
    rank_upper = np.quantile(ranks, 1.0 - alpha, axis=0)

    summary = pd.DataFrame(
        {
            system_col: systems,
            "score": arr.mean(axis=0),
            "score_ci_lower": lower,
            "score_ci_upper": upper,
            "median_rank": np.median(ranks, axis=0),
            "rank_ci_lower": rank_lower,
            "rank_ci_upper": rank_upper,
            "top1_probability": (ranks == 1.0).mean(axis=0),
            "n_tasks": n_tasks,
        }
    ).sort_values(["score", system_col], ascending=[False, True], ignore_index=True)

    pairwise = np.empty((n_systems, n_systems), dtype=float)
    for i in range(n_systems):
        for j in range(n_systems):
            greater = bootstrap_scores[:, i] > bootstrap_scores[:, j]
            equal = bootstrap_scores[:, i] == bootstrap_scores[:, j]
            pairwise[i, j] = float(np.mean(greater + 0.5 * equal))

    pairwise_frame = pd.DataFrame(pairwise, index=systems, columns=systems)
    pairwise_frame.index.name = system_col
    return summary, pairwise_frame


def task_summary(
    frame: pd.DataFrame,
    *,
    system_col: str = "system_id",
    task_col: str = "task_id",
    outcome_col: str = "resolved",
) -> pd.DataFrame:
    """Summarize task difficulty and cross-system disagreement."""

    required = {system_col, task_col, outcome_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    clean = frame[[system_col, task_col, outcome_col]].dropna().copy()
    _as_binary_array(clean[outcome_col].to_numpy())
    if clean.duplicated([system_col, task_col]).any():
        raise ValueError("expected at most one outcome per system-task pair")

    grouped = clean.groupby(task_col, sort=True)[outcome_col]
    result = grouped.agg(solve_rate="mean", n_systems="size").reset_index()
    p = result["solve_rate"].to_numpy(dtype=float)
    result["disagreement"] = 4.0 * p * (1.0 - p)

    entropy = np.zeros_like(p)
    mask = (p > 0) & (p < 1)
    entropy[mask] = -(
        p[mask] * np.log2(p[mask])
        + (1.0 - p[mask]) * np.log2(1.0 - p[mask])
    )
    result["entropy_bits"] = entropy
    return result
