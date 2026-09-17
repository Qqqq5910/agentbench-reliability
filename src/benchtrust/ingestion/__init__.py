"""Data ingestion adapters for public benchmark sources."""

from .swebench import catalog_submissions, load_submission_outcomes

__all__ = ["catalog_submissions", "load_submission_outcomes"]
