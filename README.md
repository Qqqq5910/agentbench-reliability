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

`benchtrust` now includes a reproducible Stage 1 analysis core:

- task-level percentile bootstrap confidence intervals;
- paired score-difference bootstrap that preserves task alignment;
- bootstrap leaderboard rank distributions;
- pairwise ordering-stability matrices;
- task solve-rate, disagreement, and entropy summaries;
- paired benchmark-size simulations based on the empirical joint outcome distribution and exact McNemar tests;
- validation of tidy system-task outcome tables;
- an ingestion adapter for the official `SWE-bench/experiments` repository;
- a CLI, unit tests, Ruff linting, and GitHub Actions CI.

**No empirical research conclusion is claimed yet.** The next milestone is to freeze an official SWE-bench Verified snapshot, reproduce reported scores, and generate the first Stage 1 figures.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

ruff check .
pytest -q
```

The analysis table uses one row per system-task outcome:

```text
system_id,task_id,resolved
agent_a,task_001,1
agent_a,task_002,0
agent_b,task_001,1
agent_b,task_002,1
```

Validate and analyze it with:

```bash
benchtrust validate data/processed/outcomes.parquet
benchtrust analyze data/processed/outcomes.parquet --output-dir artifacts/analysis
benchtrust power data/processed/outcomes.parquet agent_a agent_b
```

## SWE-bench ingestion

The initial public-data source is the official repository:

- `https://github.com/SWE-bench/experiments`

Recent SWE-bench leaderboard entries store `metadata.yaml` and result summaries in the experiments repository while larger artifacts may live in the submitter's public repository. Older entries may point to the public SWE-bench submissions bucket. The ingestion code preserves each leaderboard directory as a distinct `submission_id`; similar submission names are not collapsed into assumed replicates.

Given a local checkout and a trusted task-universe file containing `task_id`, normalize the data with:

```bash
benchtrust ingest-swebench \
  /path/to/experiments \
  /path/to/swebench_verified_task_ids.csv \
  --split verified \
  --output-dir data/processed
```

This writes a submission catalog and a complete submission-by-task outcome table in Parquet format.

## Stage 1 statistical design

For systems evaluated on the same tasks, analyses preserve task pairing. The baseline workflow is:

1. reproduce aggregate scores from task-level outcomes;
2. bootstrap tasks jointly across systems;
3. estimate score and rank uncertainty;
4. measure pairwise ordering stability;
5. identify tasks with high cross-system disagreement;
6. simulate how benchmark size changes detection power and rank reversals.

The paired power simulator uses the observed 2x2 joint outcome distribution for two systems rather than pretending their outcomes are independent Bernoulli draws. Its conclusions are therefore conditional on the observed task population and system pair.

## Stage 2 — controlled multi-run experiment

After Stage 1 identifies the precision requirements, the project will freeze a controlled experiment with:

- the same benchmark task;
- the same agent commit and configuration;
- the same exact model/version;
- a fixed evaluation environment;
- multiple independent executions.

Only those data will be used to estimate true same-system run-to-run stochasticity.

## Planned outputs

- a frozen public-data Stage 1 snapshot with provenance;
- publication-ready uncertainty and rank-stability figures;
- a versioned research report / preprint;
- a controlled multi-run dataset for Stage 2;
- the reusable `benchtrust` Python package.

## Repository structure

```text
agentbench-reliability/
├── .github/workflows/ci.yml
├── DATA_SCHEMA.md
├── RESEARCH_PLAN.md
├── README.md
├── docs/
├── pyproject.toml
├── src/benchtrust/
│   ├── ingestion/
│   ├── cli.py
│   ├── power.py
│   ├── statistics.py
│   └── validation.py
└── tests/
```

## Reproducibility principles

- Raw source data are immutable once snapshotted.
- Every processed table is generated from code.
- Figures and report tables must be reproducible from scripted analysis.
- Benchmark versions, system/model identifiers, source URLs, retrieval dates, and configuration metadata are retained.
- Missingness and failures are preserved rather than silently dropped.
- Exploratory analyses are separated from confirmatory Stage 2 analyses.

See `RESEARCH_PLAN.md`, `DATA_SCHEMA.md`, and `docs/SOURCES.md` for the research protocol and source-of-truth rules.

## License

MIT
