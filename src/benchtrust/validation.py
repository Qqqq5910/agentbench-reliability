from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    n_rows: int = 0
    n_systems: int = 0
    n_tasks: int = 0
    complete_task_fraction: float = 0.0

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def add(self, severity: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(severity, code, message))


def validate_outcome_table(
    frame: pd.DataFrame,
    *,
    system_col: str = "system_id",
    task_col: str = "task_id",
    outcome_col: str = "resolved",
) -> ValidationReport:
    """Validate the tidy system-task outcome table used by Stage 1 analyses."""

    report = ValidationReport(n_rows=len(frame))
    required = [system_col, task_col, outcome_col]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        report.add("error", "missing_columns", f"Missing required columns: {missing}")
        return report

    report.n_systems = int(frame[system_col].nunique(dropna=True))
    report.n_tasks = int(frame[task_col].nunique(dropna=True))

    if frame[system_col].isna().any():
        report.add("error", "missing_system_id", "system_id contains missing values")
    if frame[task_col].isna().any():
        report.add("error", "missing_task_id", "task_id contains missing values")

    duplicated = frame.duplicated([system_col, task_col], keep=False)
    if duplicated.any():
        report.add(
            "error",
            "duplicate_system_task",
            f"Found {int(duplicated.sum())} rows in duplicated system-task pairs",
        )

    outcomes = frame[outcome_col]
    invalid = outcomes.notna() & ~outcomes.isin([0, 1, False, True])
    if invalid.any():
        values = sorted({str(value) for value in outcomes[invalid].unique()})
        report.add(
            "error",
            "invalid_outcome",
            f"Outcome must be binary 0/1; invalid values: {values}",
        )

    missing_outcomes = int(outcomes.isna().sum())
    if missing_outcomes:
        report.add(
            "warning",
            "missing_outcome",
            f"Found {missing_outcomes} rows with missing outcomes",
        )

    if report.n_systems == 0 or report.n_tasks == 0:
        report.add("error", "empty_design", "No systems or tasks available for analysis")
        return report

    counts = frame.pivot_table(
        index=task_col,
        columns=system_col,
        values=outcome_col,
        aggfunc="size",
        fill_value=0,
    )
    if counts.empty:
        report.complete_task_fraction = 0.0
    else:
        complete = np.all(counts.to_numpy() == 1, axis=1)
        report.complete_task_fraction = float(np.mean(complete))
        if report.complete_task_fraction < 1.0:
            report.add(
                "warning",
                "incomplete_pairing",
                "Not every task has exactly one observation for every system; paired "
                "leaderboard analysis will use the complete-task subset.",
            )

    return report
