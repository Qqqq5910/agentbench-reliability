# Research Plan

## Working title

**One Run Is Not Enough: Measuring the Reliability of AI Coding-Agent Benchmarks**

## Motivation

Coding-agent leaderboards are commonly interpreted as if each reported score and rank were exact. In reality, evaluation contains at least two distinct sources of uncertainty:

1. **Task-sampling uncertainty** — the benchmark contains a finite set of tasks sampled from a broader task population.
2. **Run-to-run uncertainty** — stochastic agents may produce different outcomes on the same task when rerun under otherwise controlled conditions.

This project measures both sources separately and studies how they affect leaderboard conclusions.

## Research questions

### RQ1 — Run-to-run reliability
How frequently does the same agent change outcome on the same task across repeated independent runs?

### RQ2 — Rank stability
How stable are pairwise agent comparisons and complete leaderboard rankings under resampling and repeated execution?

### RQ3 — Task instability
Which observable task and trajectory characteristics predict unstable outcomes?

### RQ4 — Benchmark size and statistical power
How many tasks are required to distinguish realistic performance gaps at conventional power levels?

### RQ5 — Evaluation-budget allocation
Under a fixed number of total agent-task executions, how should budget be allocated between task breadth and repeated runs?

## Primary hypotheses

- **H1:** A non-trivial subset of benchmark tasks will have within-agent success probabilities materially different from 0 or 1.
- **H2:** Small leaderboard score gaps will often correspond to overlapping uncertainty intervals and unstable pairwise orderings.
- **H3:** Rank stability will increase nonlinearly with benchmark size.
- **H4:** The optimal breadth/repetition tradeoff will depend on the magnitude of within-task run variance.

These hypotheses are provisional until the confirmatory protocol is frozen.

## Unit of analysis

The atomic observation in the controlled experiment is one independent execution of an agent on one benchmark task.

Recommended primary key:

`benchmark_id × task_id × agent_id × model_id × config_hash × run_id`

## Primary outcome

`resolved ∈ {0,1}`

## Secondary outcomes

- wall-clock time
- token usage
- estimated cost
- trajectory length
- number of tool calls
- number of edited files
- patch size
- failure category

## Statistical analysis

### Score uncertainty

Estimate benchmark-level performance with confidence intervals rather than point estimates alone.

### Pairwise comparisons

For agents evaluated on the same tasks, preserve task pairing. Report the distribution and interval of the paired score difference.

### Rank uncertainty

Bootstrap tasks and, when repeated-run data exist, sample task outcomes from the empirical or modeled within-task success distribution. Track rank distributions and pairwise ordering probabilities.

### Run-to-run variance

Estimate task-level success probabilities and characterize tasks by instability, including entropy/variance summaries where appropriate.

### Hierarchical modeling

Model outcomes with agent and task effects, with extensions for repositories and observable task characteristics.

### Power analysis

Use simulation based on observed task heterogeneity and paired outcomes rather than relying only on independent-binomial approximations.

## Stage 1: public-data baseline

Goals:

1. ingest public coding-agent benchmark results;
2. normalize agent/model/task identities;
3. reproduce reported leaderboard scores where possible;
4. estimate task-sampling uncertainty;
5. quantify pairwise agreement/disagreement across systems;
6. simulate benchmark-size sensitivity;
7. identify data gaps that require controlled reruns.

Important limitation: different public submissions must not automatically be treated as repeated independent runs of the same system.

## Stage 2: controlled multi-run study

Proposed initial design:

- 100–200 benchmark tasks;
- 3–5 agent/model configurations;
- 5 independent runs per task/configuration;
- fixed environment and explicit versioning.

The final design will be chosen using Stage 1 power simulations and available compute budget.

## Reproducibility requirements

Record at minimum:

- benchmark name/version;
- task ID and repository;
- model provider and exact model identifier;
- agent implementation/version/commit;
- complete evaluation configuration or config hash;
- run timestamp;
- seed, if meaningful;
- environment/container identifier;
- outcome and failure state;
- resource-use measurements when available.

## Threats to validity

- benchmark tasks may not represent production software engineering;
- agent/provider behavior can change over time;
- model aliases may silently change underlying versions;
- repeated executions may not be fully independent;
- infrastructure failures can be confounded with agent failures;
- public leaderboard submissions may differ in scaffolding, prompts, or hidden settings.

## Publication target

The repository should be publication-ready even if no formal venue is selected initially. The minimum release should include a frozen dataset snapshot, reproducible analysis, generated figures, methodology, limitations, and a versioned research report.
