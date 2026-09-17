# Data Schema

This document defines the canonical tabular schema for the project. Raw source-specific files may contain additional fields, but processed datasets should map into these tables.

## `tasks`

One row per benchmark task.

| Field | Type | Description |
|---|---|---|
| `benchmark_id` | string | Benchmark and version identifier |
| `task_id` | string | Stable task identifier |
| `repository` | string | Source repository |
| `issue_id` | string/null | Source issue identifier when available |
| `language` | string/null | Primary programming language |
| `created_at` | datetime/null | Original issue/task date |
| `gold_patch_lines` | integer/null | Reference patch size if available |
| `gold_files_changed` | integer/null | Reference files changed if available |
| `metadata_json` | json | Source-specific immutable metadata |

Primary key: `(benchmark_id, task_id)`.

## `systems`

One row per unique evaluated configuration.

| Field | Type | Description |
|---|---|---|
| `system_id` | string | Canonical system identifier |
| `agent_name` | string | Agent/scaffold name |
| `agent_version` | string/null | Version or commit |
| `model_provider` | string/null | Model provider |
| `model_id` | string | Exact reported model identifier |
| `config_hash` | string/null | Hash of reproducibility-relevant configuration |
| `source` | string | Public submission or controlled experiment |
| `metadata_json` | json | Additional configuration metadata |

## `runs`

One row per individual agent-task execution.

| Field | Type | Description |
|---|---|---|
| `run_id` | string | Unique execution identifier |
| `benchmark_id` | string | Benchmark identifier |
| `task_id` | string | Task identifier |
| `system_id` | string | Evaluated system |
| `replicate_index` | integer/null | Repeated-run index when applicable |
| `resolved` | boolean/null | Primary task-resolution outcome |
| `status` | string | `completed`, `infra_error`, `timeout`, etc. |
| `started_at` | datetime/null | Start timestamp |
| `duration_s` | float/null | Wall-clock duration |
| `input_tokens` | integer/null | Input token count |
| `output_tokens` | integer/null | Output token count |
| `cost_usd` | float/null | Reported/estimated cost |
| `tool_calls` | integer/null | Tool-call count |
| `trajectory_steps` | integer/null | Number of trajectory steps |
| `files_changed` | integer/null | Produced patch file count |
| `patch_lines` | integer/null | Produced patch size |
| `failure_category` | string/null | Normalized failure class |
| `artifact_uri` | string/null | Location of detailed logs/trajectory |
| `source_submission_id` | string/null | Original public submission identifier |
| `metadata_json` | json | Remaining source metadata |

Primary key: `run_id`.

## `submissions`

One row per public leaderboard submission or controlled experiment batch.

| Field | Type | Description |
|---|---|---|
| `submission_id` | string | Canonical submission identifier |
| `benchmark_id` | string | Benchmark/version |
| `system_id` | string | System configuration |
| `submitted_at` | datetime/null | Submission date |
| `reported_score` | float/null | Score reported by source |
| `n_tasks` | integer/null | Number of evaluated tasks |
| `source_url` | string | Provenance URL |
| `is_controlled_replicate` | boolean | Whether repeated-run interpretation is justified |
| `metadata_json` | json | Additional source metadata |

## Analysis rules

1. Never infer `replicate_index` merely because two submissions share a model name.
2. Infrastructure failures remain explicit; they are not silently converted to unresolved tasks.
3. Keep exact provider/model identifiers in raw data even when a normalized family label is added later.
4. All transformations from raw source data to processed tables must be scripted and reproducible.
5. If a source does not distinguish missing results from failures, retain that ambiguity in `status` and document it.
