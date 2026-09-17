# Data Sources and Provenance

## Initial source of truth

Stage 1 starts with the official SWE-bench repositories rather than third-party leaderboard mirrors.

### SWE-bench experiments

- Repository: `https://github.com/SWE-bench/experiments`
- Role: submission registry, metadata, result summaries, and pointers to larger artifacts.
- Initial split: `evaluation/verified/`.
- Entry identity: the submission directory name is retained as `submission_id`.

The experiments repository documents that recent entries keep `metadata.yaml`, README, logo, and result summaries in the registry while predictions, execution logs, and reasoning traces may be hosted in the submitter's public repository through the metadata `assets` block. Older entries can point to the public SWE-bench submissions bucket.

### SWE-bench benchmark tasks

The task universe must come from an official SWE-bench dataset/version. A task-universe file is treated as a required input when expanding a submission's `resolved` list into binary task outcomes. This prevents an absent task ID from being interpreted as a failed task unless the denominator is explicitly known.

## Snapshot policy

Every empirical release should record:

- source repository URL;
- source commit SHA or immutable dataset revision;
- retrieval date in UTC;
- benchmark split and version;
- task-universe source and revision;
- files used to derive the processed tables;
- checksum for frozen raw snapshots when raw files are retained.

Processed datasets should include a machine-readable provenance record under `data/processed/` or `artifacts/`.

## Interpretation rules

1. A leaderboard submission is not automatically an independent experimental replicate.
2. Similar agent/model names must not be merged without configuration evidence.
3. Missing artifacts must be preserved as missingness or explicit failure categories according to the source data; they must not be silently dropped.
4. Score reproduction must be checked against the source-reported result before inferential analyses are trusted.
5. True run-to-run stochasticity requires repeated executions of a frozen system configuration and belongs to Stage 2 unless a public source demonstrably satisfies that condition.
