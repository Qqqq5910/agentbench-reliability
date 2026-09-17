# AgentBench Reliability

> **One Run Is Not Enough:** Measuring the statistical reliability, uncertainty, and ranking stability of AI coding-agent benchmarks.

AI coding-agent leaderboards usually compress evaluation into a single score. This project asks a more fundamental question: **how much should we trust small score differences and rank orderings when agents, tasks, and evaluation runs are stochastic?**

The goal is to build an open, reproducible research framework for measuring benchmark uncertainty rather than treating leaderboard scores as exact quantities.

## Research questions

1. **Run-to-run reliability** — How often does the same agent produce different outcomes on the same task across repeated runs?
2. **Rank stability** — When two agents differ by only a few percentage points, how often is that ordering statistically distinguishable?
3. **Task instability** — Which task characteristics are associated with high run-to-run variance?
4. **Benchmark sample size** — How many tasks are needed to reliably distinguish agents with small performance gaps?
5. **Breadth vs. repetition** — Under a fixed evaluation budget, is it better to evaluate more unique tasks once or fewer tasks multiple times?

## Main outputs

This repository is designed to produce four reusable artifacts:

- **A multi-run benchmark dataset** with repeated outcomes for the same agent-task pairs.
- **A reproducible statistical analysis pipeline** for confidence intervals, rank uncertainty, variance decomposition, and power analysis.
- **`benchtrust`**, a small Python package for reliability analysis of arbitrary AI benchmarks.
- **A research report / preprint** documenting methods, results, limitations, and recommendations for benchmark designers.

## Study design

The project has two stages.

### Stage 1 — Public-data baseline

Use publicly available coding-agent benchmark submissions and metadata to establish the baseline leaderboard, task-level agreement patterns, score uncertainty under task resampling, and benchmark power characteristics.

This stage intentionally separates **task-sampling uncertainty** from **true run-to-run stochasticity**. Public leaderboard submissions are useful for the former, but they should not be misrepresented as repeated independent runs of the same system unless the metadata actually supports that interpretation.

### Stage 2 — Controlled multi-run experiment

Run a selected set of benchmark tasks repeatedly under controlled conditions:

- same task
- same agent configuration
- same model/version
- fixed evaluation environment
- repeated independent runs

The primary outcome is task resolution (`resolved ∈ {0,1}`), with secondary measurements such as trajectory length, tool-call count, token usage, wall-clock time, and cost when available.

## Statistical plan

Planned methods include:

- paired bootstrap confidence intervals
- cluster bootstrap over tasks
- pairwise difference intervals
- rank-stability simulation
- permutation / randomization tests where appropriate
- hierarchical logistic regression
- variance decomposition
- mixed-effects models
- Monte Carlo power analysis
- sensitivity analyses across task subsets and benchmark sizes

A central principle is to report **uncertainty around rankings**, not just point estimates.

## Repository structure

```text
agentbench-reliability/
├── README.md
├── pyproject.toml
├── src/benchtrust/
├── configs/
├── data/
│   ├── raw/
│   └── processed/
├── notebooks/
├── experiments/
├── reports/
├── paper/
└── tests/
```

## Reproducibility principles

- Raw data are immutable once ingested.
- Every processed table is generated from code.
- Every figure in the report should be reproducible from a scripted analysis.
- Benchmark versions, model identifiers, agent versions, prompts, environment settings, seeds (when meaningful), and timestamps are recorded.
- Missingness and failed runs are preserved rather than silently dropped.
- Confirmatory analyses are separated from exploratory analyses.

## Status

**Research foundation in progress.**

The first milestone is to build the public-data ingestion pipeline and produce a statistically rigorous baseline analysis before spending compute on controlled repeated runs.

## License

MIT
