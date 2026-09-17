"""Statistical reliability analysis for AI benchmarks."""

from .power import paired_power_curve
from .statistics import (
    IntervalEstimate,
    bootstrap_leaderboard,
    paired_difference_interval,
    score_interval,
    task_summary,
)
from .validation import ValidationReport, validate_outcome_table

__all__ = [
    "IntervalEstimate",
    "ValidationReport",
    "bootstrap_leaderboard",
    "paired_difference_interval",
    "paired_power_curve",
    "score_interval",
    "task_summary",
    "validate_outcome_table",
]

__version__ = "0.1.0"
