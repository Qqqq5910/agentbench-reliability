from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import t


REQUIRED_TASK_COLUMNS = {"task_id", "solve_rate", "disagreement"}


def _validate_task_summary(frame: pd.DataFrame) -> None:
    missing = REQUIRED_TASK_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"task summary missing required columns: {sorted(missing)}")
    if frame["task_id"].duplicated().any():
        raise ValueError("task summary contains duplicate task IDs")
    if frame.empty:
        raise ValueError("task summary must not be empty")


def _repository_from_task_id(task_id: str) -> str:
    return str(task_id).split("__", 1)[0]


def _proportional_quotas(counts: pd.Series, n_total: int) -> dict[str, int]:
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    if n_total > int(counts.sum()):
        raise ValueError("cannot allocate more tasks than are available")

    raw = counts.astype(float) / float(counts.sum()) * n_total
    quotas = {str(repo): int(math.floor(value)) for repo, value in raw.items()}
    remaining = n_total - sum(quotas.values())

    ordering = sorted(
        (
            (str(repo), float(raw.loc[repo] - quotas[str(repo)]))
            for repo in counts.index
        ),
        key=lambda item: (-item[1], item[0]),
    )
    while remaining:
        progress = False
        for repo, _ in ordering:
            if quotas[repo] < int(counts.loc[repo]):
                quotas[repo] += 1
                remaining -= 1
                progress = True
                if remaining == 0:
                    break
        if not progress:
            raise ValueError("unable to allocate representative task quotas")
    return quotas


def select_stage2_tasks(
    task_summary: pd.DataFrame,
    *,
    total_tasks: int = 120,
    representative_tasks: int = 80,
    enriched_tasks: int = 40,
    disagreement_threshold: float = 0.9,
    seed: int = 20260921,
) -> pd.DataFrame:
    """Select a deterministic Stage 2 subset with representation plus disagreement enrichment."""

    _validate_task_summary(task_summary)
    if representative_tasks + enriched_tasks != total_tasks:
        raise ValueError("representative_tasks + enriched_tasks must equal total_tasks")
    if total_tasks > len(task_summary):
        raise ValueError("requested Stage 2 subset exceeds the available task universe")
    if not 0.0 <= disagreement_threshold <= 1.0:
        raise ValueError("disagreement_threshold must be between 0 and 1")

    frame = task_summary.copy()
    frame["task_id"] = frame["task_id"].astype(str)
    frame["repository"] = frame["task_id"].map(_repository_from_task_id)
    frame = frame.sort_values(["repository", "task_id"]).reset_index(drop=True)

    counts = frame.groupby("repository", sort=True).size()
    quotas = _proportional_quotas(counts, representative_tasks)
    rng = np.random.default_rng(seed)

    representative_indices: list[int] = []
    for repository in sorted(quotas):
        quota = quotas[repository]
        if quota == 0:
            continue
        candidates = frame.index[frame["repository"] == repository].to_numpy()
        chosen = rng.choice(candidates, size=quota, replace=False)
        representative_indices.extend(int(index) for index in chosen)

    representative = frame.loc[sorted(representative_indices)].copy()
    representative["selection_component"] = "representative"

    representative_ids = set(representative["task_id"])
    enrichment_pool = frame.loc[
        (frame["disagreement"] >= disagreement_threshold)
        & (~frame["task_id"].isin(representative_ids))
    ].copy()
    if len(enrichment_pool) < enriched_tasks:
        raise ValueError(
            "not enough unselected high-disagreement tasks for requested enrichment: "
            f"need {enriched_tasks}, found {len(enrichment_pool)}"
        )

    enrichment_candidates = enrichment_pool.index.to_numpy()
    enrichment_indices = rng.choice(
        enrichment_candidates,
        size=enriched_tasks,
        replace=False,
    )
    enriched = frame.loc[sorted(int(index) for index in enrichment_indices)].copy()
    enriched["selection_component"] = "high_disagreement_enrichment"

    selected = pd.concat([representative, enriched], ignore_index=True)
    selected["selection_seed"] = seed
    selected["disagreement_threshold"] = disagreement_threshold
    selected = selected.sort_values(["selection_component", "repository", "task_id"]).reset_index(
        drop=True
    )

    if len(selected) != total_tasks or selected["task_id"].duplicated().any():
        raise RuntimeError("Stage 2 task selection invariant failed")
    return selected


def _calibrated_probabilities(
    difficulty: np.ndarray,
    *,
    target_rate: float,
    temperature: float,
) -> np.ndarray:
    if not 0.0 < target_rate < 1.0:
        raise ValueError("target_rate must be strictly between 0 and 1")
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    clipped = np.clip(np.asarray(difficulty, dtype=float), 0.02, 0.98)
    base = np.log(clipped / (1.0 - clipped)) / temperature

    low = -20.0
    high = 20.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        mean_probability = float(np.mean(1.0 / (1.0 + np.exp(-(base + midpoint)))))
        if mean_probability < target_rate:
            low = midpoint
        else:
            high = midpoint

    intercept = (low + high) / 2.0
    return 1.0 / (1.0 + np.exp(-(base + intercept)))


def _exact_ordering_probabilities(
    p_a: np.ndarray,
    p_b: np.ndarray,
) -> tuple[float, float, float]:
    distribution = np.array([1.0], dtype=float)
    for probability_a, probability_b in zip(p_a, p_b, strict=True):
        negative = (1.0 - probability_a) * probability_b
        zero = (
            probability_a * probability_b
            + (1.0 - probability_a) * (1.0 - probability_b)
        )
        positive = probability_a * (1.0 - probability_b)
        distribution = np.convolve(distribution, np.array([negative, zero, positive]))

    zero_index = len(p_a)
    reversal = float(distribution[:zero_index].sum())
    tie = float(distribution[zero_index])
    forward = float(distribution[zero_index + 1 :].sum())
    return reversal, tie, forward


def simulate_replicate_design(
    task_subset: pd.DataFrame,
    *,
    candidate_replicates: Sequence[int] = (3, 5, 7, 10),
    scenarios: Mapping[str, float] | None = None,
    target_rate_a: float = 0.75,
    target_rate_b: float = 0.72,
    n_sim: int = 5_000,
    seed: int = 20260921,
) -> pd.DataFrame:
    """Simulate Stage 2 replicate precision under explicit synthetic stochasticity scenarios.

    Stage 1 cross-system solve rates are used only as a task-difficulty shape. They are not
    interpreted as estimates of within-system rerun probabilities.
    """

    _validate_task_summary(task_subset)
    if n_sim <= 0:
        raise ValueError("n_sim must be positive")
    scenario_temperatures = dict(
        scenarios or {"low": 0.65, "moderate": 1.0, "high": 1.5}
    )
    if not scenario_temperatures:
        raise ValueError("at least one stochasticity scenario is required")

    difficulty = task_subset["solve_rate"].to_numpy(dtype=float)
    n_tasks = len(difficulty)
    rows: list[dict[str, float | int | str]] = []

    for scenario_index, (scenario, temperature) in enumerate(scenario_temperatures.items()):
        p_a = _calibrated_probabilities(
            difficulty,
            target_rate=target_rate_a,
            temperature=float(temperature),
        )
        p_b = _calibrated_probabilities(
            difficulty,
            target_rate=target_rate_b,
            temperature=float(temperature),
        )
        true_score_a = float(p_a.mean())
        true_score_b = float(p_b.mean())
        true_difference = true_score_a - true_score_b
        true_run_sd_a = float(np.sqrt(np.sum(p_a * (1.0 - p_a))) / n_tasks)
        reversal, tie, _ = _exact_ordering_probabilities(p_a, p_b)

        unstable_mask = (p_a >= 0.2) & (p_a <= 0.8)
        stable_mask = (p_a <= 0.05) | (p_a >= 0.95)

        for replicate_count in candidate_replicates:
            replicates = int(replicate_count)
            if replicates < 2:
                raise ValueError("candidate replicate counts must be at least 2")

            rng = np.random.default_rng(seed + scenario_index * 10_000 + replicates)
            shape = (n_sim, replicates, n_tasks)
            draws_a = rng.random(shape) < p_a
            draws_b = rng.random(shape) < p_b

            scores_a = draws_a.mean(axis=2)
            scores_b = draws_b.mean(axis=2)
            differences = scores_a - scores_b

            mean_score_a = scores_a.mean(axis=1)
            score_abs_error = np.abs(mean_score_a - true_score_a)

            run_sd_estimate = scores_a.std(axis=1, ddof=1)
            run_sd_relative_error = np.abs(run_sd_estimate - true_run_sd_a) / max(
                true_run_sd_a,
                1e-12,
            )

            difference_mean = differences.mean(axis=1)
            difference_sd = differences.std(axis=1, ddof=1)
            critical_value = float(t.ppf(0.975, df=replicates - 1))
            difference_halfwidth = critical_value * difference_sd / math.sqrt(replicates)
            detection_power = float(
                np.mean(np.abs(difference_mean) > difference_halfwidth)
            )

            reversal_estimate = np.mean(differences < 0, axis=1)
            reversal_abs_error = np.abs(reversal_estimate - reversal)

            task_varies = draws_a.min(axis=1) != draws_a.max(axis=1)
            if unstable_mask.any():
                unstable_detection = task_varies[:, unstable_mask].mean(axis=1)
                unstable_detection_mean = float(unstable_detection.mean())
            else:
                unstable_detection_mean = float("nan")

            if stable_mask.any():
                stable_false_positive = task_varies[:, stable_mask].mean(axis=1)
                stable_false_positive_mean = float(stable_false_positive.mean())
            else:
                stable_false_positive_mean = float("nan")

            rows.append(
                {
                    "scenario": scenario,
                    "temperature": float(temperature),
                    "replicates": replicates,
                    "n_tasks": n_tasks,
                    "n_sim": n_sim,
                    "target_rate_a": target_rate_a,
                    "target_rate_b": target_rate_b,
                    "true_score_a": true_score_a,
                    "true_score_b": true_score_b,
                    "true_score_difference": true_difference,
                    "true_run_sd_a": true_run_sd_a,
                    "true_rank_reversal_probability": reversal,
                    "true_tie_probability": tie,
                    "score_abs_error_p95": float(np.quantile(score_abs_error, 0.95)),
                    "run_sd_median_relative_error": float(
                        np.median(run_sd_relative_error)
                    ),
                    "paired_diff_ci_median_halfwidth": float(
                        np.median(difference_halfwidth)
                    ),
                    "paired_diff_detection_power": detection_power,
                    "rank_reversal_median_abs_error": float(
                        np.median(reversal_abs_error)
                    ),
                    "unstable_task_fraction": float(unstable_mask.mean()),
                    "unstable_detection_mean": unstable_detection_mean,
                    "stable_task_fraction": float(stable_mask.mean()),
                    "stable_false_positive_mean": stable_false_positive_mean,
                }
            )

    return pd.DataFrame(rows)


def recommend_replicates(
    simulation: pd.DataFrame,
    *,
    primary_scenario: str,
    thresholds: Mapping[str, float],
) -> tuple[int | None, pd.DataFrame]:
    """Return the smallest candidate meeting all pre-registered primary-scenario thresholds."""

    required = {
        "score_abs_error_p95",
        "run_sd_median_relative_error",
        "paired_diff_ci_median_halfwidth",
        "unstable_detection_mean",
        "rank_reversal_median_abs_error",
    }
    missing = required - set(thresholds)
    if missing:
        raise ValueError(f"replicate thresholds missing keys: {sorted(missing)}")

    result = simulation.copy()
    primary_mask = result["scenario"] == primary_scenario
    if not primary_mask.any():
        raise ValueError(f"primary scenario not found: {primary_scenario}")

    result["meets_primary_precision"] = False
    result.loc[primary_mask, "meets_primary_precision"] = (
        (
            result.loc[primary_mask, "score_abs_error_p95"]
            <= thresholds["score_abs_error_p95"]
        )
        & (
            result.loc[primary_mask, "run_sd_median_relative_error"]
            <= thresholds["run_sd_median_relative_error"]
        )
        & (
            result.loc[primary_mask, "paired_diff_ci_median_halfwidth"]
            <= thresholds["paired_diff_ci_median_halfwidth"]
        )
        & (
            result.loc[primary_mask, "unstable_detection_mean"]
            >= thresholds["unstable_detection_mean"]
        )
        & (
            result.loc[primary_mask, "rank_reversal_median_abs_error"]
            <= thresholds["rank_reversal_median_abs_error"]
        )
    )

    eligible = result.loc[primary_mask & result["meets_primary_precision"], "replicates"]
    recommendation = None if eligible.empty else int(eligible.min())
    return recommendation, result
