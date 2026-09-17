"""Data ingestion adapters for public benchmark sources."""

from .huggingface import fetch_swebench_verified_task_universe
from .swebench import (
    catalog_submissions,
    load_submission_outcomes,
    reproduce_submission_scores,
)

__all__ = [
    "catalog_submissions",
    "fetch_swebench_verified_task_universe",
    "load_submission_outcomes",
    "reproduce_submission_scores",
]
