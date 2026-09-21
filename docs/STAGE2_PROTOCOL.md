# Stage 2 controlled repeated-run protocol

Status: **draft pre-registration**. This document freezes the analysis design that can be specified before Stage 1 finishes. The task subset and exact system configurations must not be finalized until a successful frozen Stage 1 artifact exists.

## Objective

Measure **run-to-run stochasticity** of coding agents separately from the **task-sampling uncertainty** already studied in Stage 1.

Stage 1 asks: if the benchmark task sample changed, how stable would leaderboard scores and ranks be?

Stage 2 asks: if we rerun the same frozen agent configuration on the same task, how often does the outcome change?

These two uncertainty sources must never be pooled or described as interchangeable.

## Primary estimands

For each frozen system configuration:

1. Per-task solve probability across repeated executions.
2. Mean benchmark solve rate across repeated executions.
3. Between-run variance of aggregate benchmark score.
4. Probability that a pairwise ordering reverses across repeated runs.
5. Reliability of a reported single-run score as an estimator of repeated-run performance.

For each system pair:

1. Paired difference in solve probability on the same tasks.
2. Probability that system A outperforms system B across replicated benchmark runs.
3. Probability that the sign of the observed score difference changes across reruns.

## Experimental unit and blocking

- Primary experimental unit: one **system × task × replicate** execution.
- Task is a blocking factor shared across systems.
- System comparisons must preserve task pairing.
- Replicates for the same system-task cell must use independent random seeds when the runtime exposes one.
- Execution order should be randomized within resource constraints to reduce temporal/provider drift confounding.

## System configuration freeze

Stage 2 will evaluate **3–5 configurations**.

A configuration is not just a model name. The frozen record must include:

- agent/scaffold name and version or commit;
- exact model/provider identifier;
- system prompt or prompt-template hash;
- tool configuration;
- benchmark harness version;
- container/environment identifier;
- decoding and reasoning settings when exposed;
- timeout and retry policy;
- seed when meaningful;
- any provider-side mode that can alter behavior.

Two executions are considered replicates only when all reproducibility-relevant fields above are frozen.

## Task subset selection

Task selection is intentionally deferred until the successful Stage 1 snapshot is available.

The selection rule must be scripted and deterministic.

The final subset should include:

1. a representative random component from the full SWE-bench Verified task universe;
2. a pre-specified enrichment component from tasks with high cross-system disagreement in Stage 1;
3. no manual cherry-picking based on desired system outcomes.

The exact random seed, sample size, enrichment fraction, and selected task IDs must be written to a frozen config before controlled runs begin.

## Replicate-count selection

Replicate count will be chosen by simulation before compute is spent.

Candidate replicate counts: 3, 5, 7, 10.

The simulation must evaluate at least:

- precision of per-system mean solve rate;
- precision of between-run standard deviation;
- power / precision for paired system differences;
- probability of correctly detecting materially unstable tasks;
- expected uncertainty in pairwise ordering-reversal probability.

The selected replicate count must be the smallest count meeting the pre-specified precision target, not the count that produces the most favorable result.

## Primary outcome

Primary binary outcome:

- `resolved = 1` when the benchmark task passes the official evaluation;
- `resolved = 0` for a completed agent attempt that fails the benchmark.

Infrastructure failures are **not** silently converted to unresolved agent attempts.

## Infrastructure failures

Use explicit statuses including:

- `completed`
- `infra_error`
- `provider_error`
- `timeout`
- `harness_error`
- `invalid_artifact`

Primary confirmatory analysis excludes executions that never constitute a valid agent attempt because of infrastructure failure.

A sensitivity analysis must report results under a conservative policy that counts selected non-agent failures as unresolved when scientifically defensible.

All retry rules must be frozen before execution.

## Confirmatory analyses

### A. Run-to-run score variability

For each system:

- distribution of aggregate solve rate across replicated benchmark runs;
- mean;
- standard deviation;
- 95% interval;
- minimum and maximum observed replicated score.

### B. Task-level instability

For each system-task cell:

- empirical solve probability;
- binary entropy;
- classification as stable-success, stable-failure, or unstable using pre-registered thresholds.

### C. Pairwise replicated comparison

For each system pair:

- paired task difference for each replicate;
- bootstrap interval preserving task pairing;
- replicated ordering-reversal frequency;
- probability that a single observed run gives the opposite ordering from the replicated mean ordering.

### D. Single-run reliability

Estimate how much error is introduced when a leaderboard reports one execution rather than repeated executions.

Report:

- expected absolute deviation of a single-run score from replicated mean;
- 95th percentile absolute deviation;
- probability that two near-tied systems swap order because of run stochasticity alone.

## Secondary analyses

Secondary/exploratory analyses may include:

- instability by repository;
- instability by language;
- instability by task difficulty;
- interaction between task-sampling uncertainty and run stochasticity;
- failure-category analysis;
- cost/reliability trade-offs;
- model-family or scaffold-family comparisons.

These must be labeled exploratory.

## Multiple comparisons

Pairwise confirmatory comparisons among the frozen 3–5 systems must use a pre-specified multiplicity adjustment.

Default: Holm correction across pairwise confirmatory tests.

Unadjusted intervals may also be shown for descriptive purposes, clearly labeled.

## Missingness

Every missing run must have a reason.

Do not impute missing agent outcomes unless a separate sensitivity analysis explicitly defines the imputation rule.

The report must include a missingness table by system and failure category.

## Reproducibility requirements

Before controlled execution begins, the repository must contain:

- frozen Stage 2 YAML config;
- selected task IDs;
- exact system configurations;
- replicate count and simulation output used to justify it;
- environment and harness versions;
- execution-order randomization seed;
- retry/failure policy;
- primary/secondary analysis declarations.

After execution, publish:

- raw run manifest;
- normalized run table;
- provenance metadata;
- analysis script;
- generated figures;
- versioned research report.

## Stop rule

Do not inspect interim results to decide whether to add or remove replicates for statistical significance.

If execution must stop for budget, provider, or infrastructure reasons, document the external reason and analyze the frozen completed subset with that limitation stated.

## Stage 2 entry gate

Controlled compute may begin only when all of the following are true:

1. Stage 1 workflow completes successfully on the current main branch.
2. Stage 1 frozen artifacts are published.
3. The task-selection script produces a deterministic task list from the frozen Stage 1 snapshot.
4. Candidate systems are recorded with exact reproducibility metadata.
5. Replicate-count simulation is committed.
6. This protocol is updated from draft to **FROZEN** before the first controlled run.
