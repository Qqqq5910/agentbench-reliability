from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy.stats import binom


def _paired_outcomes(
    frame: pd.DataFrame,
    system_a: str,
    system_b: str,
    *,
    system_col: str,
    task_col: str,
    outcome_col: str,
) -> np.ndarray:
    subset = frame[frame[system_col].isin([system_a, system_b])][
        [system_col, task_col, outcome_col]
    ].copy()
    if subset.duplicated([system_col, task_col]).any():
        raise ValueError("expected at most one outcome per system-task pair")
    pivot = subset.pivot(index=task_col, columns=system_col, values=outcome_col)
    if system_a not in pivot.columns or system_b not in pivot.columns:
        raise ValueError("both systems must be present")
    pivot = pivot[[system_a, system_b]].dropna()
    if pivot.empty:
        raise ValueError("no paired tasks remain after alignment")
    arr = pivot.to_numpy(dtype=float)
    if not np.isin(arr, [0.0, 1.0]).all():
        raise ValueError("outcomes must contain only 0/1 values")
    return arr


def _mcnemar_exact_pvalue(b: np.ndarray, c: np.ndarray) -> np.ndarray:
    discordant = b + c
    smaller = np.minimum(b, c)
    p = np.ones_like(discordant, dtype=float)
    mask = discordant > 0
    p[mask] = np.minimum(
        1.0,
        2.0 * binom.cdf(smaller[mask], discordant[mask], 0.5),
    )
    return p


def paired_power_curve(
    frame: pd.DataFrame,
    system_a: str,
    system_b: str,
    sample_sizes: Iterable[int],
    *,
    system_col: str = "system_id",
    task_col: str = "task_id",
    outcome_col: str = "resolved",
    n_sim: int = 5_000,
    alpha: float = 0.05,
    seed: int | None = 0,
) -> pd.DataFrame:
    """Estimate benchmark-size sensitivity from an empirical paired outcome table.

    The observed 2x2 joint outcome distribution is treated as an empirical task
    population. New benchmark task sets are sampled from that joint distribution and
    compared using an exact McNemar test. This preserves the observed dependence
    between systems instead of assuming independent Bernoulli outcomes.

    The returned power is conditional on the source systems and task population; it is
    not a universal property of a nominal score gap.
    """

    if n_sim < 100:
        raise ValueError("n_sim must be at least 100")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    arr = _paired_outcomes(
        frame,
        system_a,
        system_b,
        system_col=system_col,
        task_col=task_col,
        outcome_col=outcome_col,
    )
    probabilities = np.array(
        [
            np.mean((arr[:, 0] == 0) & (arr[:, 1] == 0)),
            np.mean((arr[:, 0] == 0) & (arr[:, 1] == 1)),
            np.mean((arr[:, 0] == 1) & (arr[:, 1] == 0)),
            np.mean((arr[:, 0] == 1) & (arr[:, 1] == 1)),
        ],
        dtype=float,
    )
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int]] = []

    for n_tasks_raw in sample_sizes:
        n_tasks = int(n_tasks_raw)
        if n_tasks <= 0:
            raise ValueError("sample sizes must be positive")
        counts = rng.multinomial(n_tasks, probabilities, size=n_sim)
        b = counts[:, 1]  # A=0, B=1
        c = counts[:, 2]  # A=1, B=0
        pvalues = _mcnemar_exact_pvalue(b, c)
        differences = (c - b) / n_tasks
        rows.append(
            {
                "n_tasks": n_tasks,
                "power_mcnemar_exact": float(np.mean(pvalues < alpha)),
                "mean_score_difference": float(np.mean(differences)),
                "rank_reversal_probability": float(np.mean(differences < 0)),
                "tie_probability": float(np.mean(differences == 0)),
                "empirical_p_a": float(arr[:, 0].mean()),
                "empirical_p_b": float(arr[:, 1].mean()),
                "paired_tasks_source": int(arr.shape[0]),
            }
        )

    return pd.DataFrame(rows)
