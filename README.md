# AgentBench Reliability

> **One Run Is Not Enough:** Measuring the statistical reliability, uncertainty, and ranking stability of AI coding-agent benchmarks.

AI coding-agent leaderboards report precise-looking scores and ranks. This project asks a more fundamental question: **how much of that ordering should we actually trust?**

The project separates two sources of uncertainty that are often conflated:

- **task-sampling uncertainty** — how leaderboard conclusions change when the evaluated task set changes;
- **run-to-run stochasticity** — how the same frozen agent/model configuration changes when the same task is rerun independently.

Stage 1 studies the first problem with public coding-agent benchmark data. Stage 2 will measure the second with a controlled repeated-run experiment. Public submissions are **not** treated as repeated runs unless their metadata supports that interpretation.

## Research questions

1. **Run-to-run reliability** — How often does the same agent produce different outcomes on the same task across repeated runs?
2. **Rank stability** — When systems differ by only a few percentage points, how stable is their ordering under task resampling?
3. **Task instability** — Which tasks create the most disagreement between systems, and later, within the same system across repeated runs?
4. **Benchmark sample size** — How many tasks are needed to distinguish realistic performance gaps with useful precision?
5. **Breadth vs. repetition** — Under a fixed evaluation budget, when should benchmark designers prefer more unique tasks versus repeated runs?

## Current implementation

`benchtrust` now provides a reproducible Stage 1 pipeline:

- pinned retrieval of the official 500-task `SWE-bench/SWE-bench_Verified` dataset;
- SHA-256 verification and machine-readable provenance manifests;
- pinned ingestion of the official `SWE-bench/experiments` registry;
- independent reconstruction of task-level aggregate scores against official metadata;
- an explicit **single-attempt primary cohort** so best-of-k submissions are not silently mixed with single-attempt systems;
- task-level percentile bootstrap confidence intervals;
- paired score-difference bootstrap that preserves task alignment;
- bootstrap leaderboard rank distributions and pairwise ordering stability;
- task solve-rate, disagreement, and entropy summaries;
- paired benchmark-size simulations based on the empirical joint outcome distribution and exact McNemar tests;
- memory-bounded leaderboard bootstrap suitable for many systems;
- validation, CLI commands, unit tests, Ruff linting, and GitHub Actions CI.

**No empirical research conclusion is claimed yet.** The frozen pipeline is ready; the next research milestone is to execute the pinned Stage 1 snapshot, publish the first uncertainty figures, and write the results section from those artifacts.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

ruff check .
pytest -q
```

Install the optional research tooling when fetching the pinned Hugging Face dataset:

```bash
python -m pip install -e ".[dev,research]"
```

## Frozen Stage 1 snapshot

The initial empirical study is pinned in `configs/swebench_verified_stage1.yaml`.

As of the frozen study definition, it uses:

- `SWE-bench/SWE-bench_Verified` at revision `78f471bf655a3137b2e8a75af1501690ec009ec3`;
- the Verified Parquet file with SHA-256 `030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25`;
- `SWE-bench/experiments` at commit `40f164d5b8f1d249bf95a6df8b74b577fd8e519d`;
- 10,000 task-bootstrap samples with seed `20260917` for the primary analysis.

Fetch the task universe:

```bash
benchtrust fetch-swebench-verified --output-dir data/raw/swebench_verified
```

Then check out the exact experiments revision and normalize the registry:

```bash
git clone https://github.com/SWE-bench/experiments external/swebench-experiments
git -C external/swebench-experiments checkout 40f164d5b8f1d249bf95a6df8b74b577fd8e519d

benchtrust ingest-swebench \
  external/swebench-experiments \
  data/raw/swebench_verified/swebench_verified_task_ids.csv \
  --experiments-revision 40f164d5b8f1d249bf95a6df8b74b577fd8e519d \
  --split verified \
  --output-dir data/processed
```

The ingestion step verifies the local Git revision, reproduces scores, writes provenance checksums, and emits both all ingestible submissions and the primary single-attempt cohort.

See [`docs/STAGE1_RUNBOOK.md`](docs/STAGE1_RUNBOOK.md) for the complete reproduction workflow.

## Analyze the primary cohort

```bash
benchtrust validate data/processed/swebench_verified_primary_outcomes.parquet

benchtrust analyze \
  data/processed/swebench_verified_primary_outcomes.parquet \
  --output-dir artifacts/stage1 \
  --n-boot 10000 \
  --seed 20260917
```

The main outputs are:

- `leaderboard_bootstrap.csv` — point estimates, score intervals, rank intervals, and top-rank frequency;
- `pairwise_ordering_probability.csv` — bootstrap ordering frequency for every system pair;
- `task_summary.csv` — task difficulty and cross-system disagreement metrics.

The pairwise bootstrap frequency is a resampling statistic, **not** a Bayesian posterior probability that one system is intrinsically better than another.

## Benchmark-size sensitivity

For a specific pair of submissions:

```bash
benchtrust power \
  data/processed/swebench_verified_primary_outcomes.parquet \
  SYSTEM_A SYSTEM_B \
  --sample-sizes 25,50,100,200,500,1000,2000 \
  --n-sim 10000 \
  --seed 20260917
```

The simulator preserves the observed paired 2x2 outcome distribution instead of assuming independent Bernoulli outcomes. Its result is conditional on that system pair and observed task population.

## Stage 1 statistical design

For systems evaluated on the same tasks, analyses preserve task pairing. The baseline workflow is:

1. pin benchmark and registry source revisions;
2. reconstruct task-level outcomes and reproduce official scores;
3. define a comparable primary cohort before inference;
4. bootstrap tasks jointly across systems;
5. estimate score and rank uncertainty;
6. measure pairwise ordering stability;
7. identify tasks with high cross-system disagreement;
8. simulate how benchmark size changes detection power and rank reversals.

Stage 1 estimates **task-sampling uncertainty**. It does not estimate true same-system rerun variance.

## Stage 2 — controlled multi-run experiment

After Stage 1 establishes precision requirements, the project will freeze a controlled experiment with:

- the same benchmark task;
- the same agent commit and configuration;
- the same exact model/version;
- a fixed evaluation environment;
- multiple independent executions.

Only those data will be used to estimate true same-system run-to-run stochasticity and to answer the breadth-vs-repetition question empirically.

## Repository structure

```text
agentbench-reliability/
├── .github/workflows/ci.yml
├── configs/
│   └── swebench_verified_stage1.yaml
├── docs/
│   ├── SOURCES.md
│   └── STAGE1_RUNBOOK.md
├── DATA_SCHEMA.md
├── RESEARCH_PLAN.md
├── README.md
├── pyproject.toml
├── src/benchtrust/
│   ├── ingestion/
│   ├── cli.py
│   ├── cohorts.py
│   ├── power.py
│   ├── provenance.py
│   ├── statistics.py
│   └── validation.py
└── tests/
```

## Reproducibility principles

- Raw source data are immutable once snapshotted.
- Reportable datasets use explicit upstream revisions rather than moving `main` branches.
- Downloaded source files are checksum-verified.
- Every processed table is generated from code.
- Every score used for inference must first pass reproduction checks.
- Figures and report tables must be reproducible from scripted analysis.
- Benchmark versions, system/model identifiers, source URLs, retrieval dates, and configuration metadata are retained.
- Missingness and failures are preserved rather than silently dropped.
- Exploratory analyses are separated from confirmatory Stage 2 analyses.

See `RESEARCH_PLAN.md`, `DATA_SCHEMA.md`, and `docs/SOURCES.md` for the research protocol and source-of-truth rules.

## Planned outputs

- a frozen Stage 1 public-data snapshot with provenance;
- publication-ready uncertainty and rank-stability figures;
- a versioned research report / preprint;
- a controlled multi-run dataset for Stage 2;
- the reusable `benchtrust` Python package.

## License

MIT
