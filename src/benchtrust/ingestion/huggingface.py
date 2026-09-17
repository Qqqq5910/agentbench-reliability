from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from benchtrust.provenance import sha256_file

SWE_BENCH_VERIFIED_REPO = "SWE-bench/SWE-bench_Verified"
SWE_BENCH_VERIFIED_REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
SWE_BENCH_VERIFIED_FILENAME = "data/test-00000-of-00001.parquet"
SWE_BENCH_VERIFIED_SHA256 = "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"


def fetch_swebench_verified_task_universe(
    output_dir: str | Path,
    *,
    revision: str = SWE_BENCH_VERIFIED_REVISION,
    expected_sha256: str = SWE_BENCH_VERIFIED_SHA256,
) -> tuple[Path, Path]:
    """Fetch a pinned official SWE-bench Verified dataset and export its task IDs.

    Network access is isolated in this function so the core statistics package remains
    usable without Hugging Face dependencies. The downloaded Parquet file is checked
    against the expected content digest before any task universe is derived from it.
    """

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - dependency error is environment-specific
        raise RuntimeError(
            "huggingface_hub is required for dataset fetching; install benchtrust[research]"
        ) from exc

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    cached_path = Path(
        hf_hub_download(
            repo_id=SWE_BENCH_VERIFIED_REPO,
            filename=SWE_BENCH_VERIFIED_FILENAME,
            repo_type="dataset",
            revision=revision,
        )
    )

    digest = sha256_file(cached_path)
    if digest != expected_sha256:
        raise ValueError(
            "SWE-bench Verified checksum mismatch: "
            f"expected {expected_sha256}, observed {digest}"
        )

    parquet_path = destination / "swebench_verified.parquet"
    shutil.copyfile(cached_path, parquet_path)

    frame = pd.read_parquet(parquet_path)
    if "instance_id" not in frame.columns:
        raise ValueError("official dataset is missing required instance_id column")
    if frame["instance_id"].isna().any() or frame["instance_id"].duplicated().any():
        raise ValueError("official dataset contains missing or duplicate instance_id values")

    task_ids = frame["instance_id"].astype(str)
    task_path = destination / "swebench_verified_task_ids.csv"
    pd.DataFrame({"task_id": task_ids}).to_csv(task_path, index=False)
    return parquet_path, task_path
