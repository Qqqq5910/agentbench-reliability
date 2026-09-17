# Stage 1 Reproduction Runbook

This runbook freezes the first empirical study to SWE-bench Verified and the source revisions in `configs/swebench_verified_stage1.yaml`.

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,research]"
```

## 2. Fetch the pinned 500-task universe

```bash
benchtrust fetch-swebench-verified \
  --output-dir data/raw/swebench_verified
```

The command downloads the official `SWE-bench/SWE-bench_Verified` Parquet file at the pinned revision, verifies its SHA-256 digest, exports `instance_id` as `task_id`, and writes a provenance manifest.

## 3. Check out the frozen experiments registry

```bash
mkdir -p external
git clone https://github.com/SWE-bench/experiments external/swebench-experiments
git -C external/swebench-experiments checkout 40f164d5b8f1d249bf95a6df8b74b577fd8e519d
```

Do not replace the pinned commit with `main` when producing reportable results.

## 4. Normalize submissions and reproduce scores

```bash
benchtrust ingest-swebench \
  external/swebench-experiments \
  data/raw/swebench_verified/swebench_verified_task_ids.csv \
  --experiments-revision 40f164d5b8f1d249bf95a6df8b74b577fd8e519d \
  --split verified \
  --output-dir data/processed
```

This step fails if the local experiments checkout is not at the declared commit, or if reconstructed result counts / independently reported metadata scores disagree.

Key outputs:

- `swebench_verified_submissions.parquet` — complete catalog of ingestible registry entries;
- `swebench_verified_outcomes.parquet` — all normalized submission-task outcomes;
- `swebench_verified_score_reproduction.csv` — score reproduction checks;
- `swebench_verified_primary_submissions.parquet` — primary single-attempt cohort;
- `swebench_verified_primary_outcomes.parquet` — task-level outcomes for the primary cohort;
- `swebench_verified_provenance.json` — revisions, checksums, and snapshot sizes.

## 5. Validate the primary outcome table

```bash
benchtrust validate data/processed/swebench_verified_primary_outcomes.parquet
```

The main analysis should not proceed if duplicate system-task pairs or invalid outcomes are present.

## 6. Run Stage 1 uncertainty analysis

```bash
benchtrust analyze \
  data/processed/swebench_verified_primary_outcomes.parquet \
  --output-dir artifacts/stage1 \
  --n-boot 10000 \
  --seed 20260917
```

This generates:

- `leaderboard_bootstrap.csv`;
- `pairwise_ordering_probability.csv`;
- `task_summary.csv`.

Task rows are resampled jointly across all systems so system comparisons remain paired. The implementation uses batched multinomial bootstrap counts to avoid allocating a large three-dimensional bootstrap tensor.

## 7. Pair-specific benchmark-size analysis

Choose two `submission_id` values from the primary catalog and run:

```bash
benchtrust power \
  data/processed/swebench_verified_primary_outcomes.parquet \
  SYSTEM_A SYSTEM_B \
  --sample-sizes 25,50,100,200,500,1000,2000 \
  --n-sim 10000 \
  --seed 20260917 \
  --output-path artifacts/stage1/power_SYSTEM_A_vs_SYSTEM_B.csv
```

The simulator preserves the observed paired 2x2 outcome distribution and uses exact McNemar tests. The resulting power curve is conditional on that system pair and observed task population; it must not be described as a universal power curve for all systems with the same nominal score gap.

## 8. Interpretation boundary

Stage 1 estimates **task-sampling uncertainty** in public leaderboard outcomes. It does not estimate true same-system run-to-run stochasticity because public submissions are not assumed to be repeated independent executions of a frozen system.

True repeated-run variance belongs to the controlled Stage 2 experiment.
