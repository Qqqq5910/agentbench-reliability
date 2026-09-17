from datetime import datetime, timezone
from pathlib import Path

from benchtrust.provenance import build_manifest, sha256_file, write_manifest


def test_sha256_file_known_content(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("agentbench\n", encoding="utf-8")
    assert sha256_file(path) == "7249967ca0e25850417d627299704f747267ad8f62a63a90853d3190e1aeb971"


def test_manifest_records_pinned_sources_and_file_hash(tmp_path: Path) -> None:
    path = tmp_path / "tasks.csv"
    path.write_text("task_id\ntask-1\n", encoding="utf-8")
    created = datetime(2026, 9, 17, 6, 0, tzinfo=timezone.utc)
    manifest = build_manifest(
        benchmark="swe-bench",
        benchmark_split="verified",
        sources=[
            {
                "name": "SWE-bench experiments",
                "url": "https://github.com/SWE-bench/experiments",
                "revision": "abc123",
            }
        ],
        files=[path],
        created_at=created,
    )
    assert manifest["created_at_utc"] == "2026-09-17T06:00:00+00:00"
    assert manifest["sources"][0]["revision"] == "abc123"
    assert manifest["files"][0]["sha256"] == sha256_file(path)

    output = write_manifest(manifest, tmp_path / "manifest.json")
    assert output.is_file()
    assert output.read_text(encoding="utf-8").endswith("\n")
