from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a local file."""

    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    benchmark: str,
    benchmark_split: str,
    sources: list[dict[str, Any]],
    files: list[str | Path] | None = None,
    created_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable provenance manifest for a frozen analysis snapshot."""

    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    file_records: list[dict[str, Any]] = []
    for raw_path in files or []:
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        file_records.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": benchmark,
        "benchmark_split": benchmark_split,
        "created_at_utc": timestamp.astimezone(UTC).isoformat(),
        "sources": sources,
        "files": file_records,
    }
    if extra:
        manifest["extra"] = extra
    return manifest


def write_manifest(manifest: dict[str, Any], output_path: str | Path) -> Path:
    """Write a provenance manifest as stable, human-readable JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
