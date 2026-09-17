from __future__ import annotations

import pandas as pd


def select_single_attempt_cohort(
    catalog: pd.DataFrame,
    outcomes: pd.DataFrame,
    reproduction: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select the primary single-attempt cohort for leaderboard uncertainty analysis.

    Multi-attempt submissions can encode a materially different evaluation policy from
    single-attempt systems. The primary Stage 1 cohort therefore keeps only submissions
    whose metadata declares exactly one attempt and whose reconstructed result counts
    are internally consistent. If an independent official score is available, it must
    also match the reconstruction.
    """

    catalog_required = {"submission_id", "attempts"}
    outcomes_required = {"submission_id"}
    reproduction_required = {
        "submission_id",
        "resolved_count_matches",
        "reported_score_available",
        "reported_score_matches",
    }
    missing_catalog = catalog_required - set(catalog.columns)
    missing_outcomes = outcomes_required - set(outcomes.columns)
    missing_reproduction = reproduction_required - set(reproduction.columns)
    if missing_catalog:
        raise ValueError(f"catalog missing required columns: {sorted(missing_catalog)}")
    if missing_outcomes:
        raise ValueError(f"outcomes missing required columns: {sorted(missing_outcomes)}")
    if missing_reproduction:
        raise ValueError(
            f"reproduction table missing required columns: {sorted(missing_reproduction)}"
        )

    checks = reproduction[
        [
            "submission_id",
            "resolved_count_matches",
            "reported_score_available",
            "reported_score_matches",
        ]
    ]
    merged = catalog.merge(checks, on="submission_id", how="left", validate="one_to_one")
    score_ok = (~merged["reported_score_available"].fillna(False)) | merged[
        "reported_score_matches"
    ].fillna(False)
    eligible = (
        merged["attempts"].eq(1)
        & merged["resolved_count_matches"].fillna(False)
        & score_ok
    )

    selected_catalog = merged.loc[eligible].copy()
    selected_ids = set(selected_catalog["submission_id"].astype(str))
    selected_outcomes = outcomes[
        outcomes["submission_id"].astype(str).isin(selected_ids)
    ].copy()
    return selected_catalog.reset_index(drop=True), selected_outcomes.reset_index(drop=True)
