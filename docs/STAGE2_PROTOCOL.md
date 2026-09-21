# Stage 2 controlled repeated-run protocol

Status: **PARTIALLY FROZEN** — the formal task subset and replicate count are frozen.
Exact system configurations remain candidate-only until the non-confirmatory pilot gate passes.

## Objective

Measure **run-to-run stochasticity** of coding agents separately from the
**task-sampling uncertainty** quantified in Stage 1.

Stage 1 asks whether leaderboard results are stable when the benchmark task sample
changes. Stage 2 asks whether the same frozen coding-agent configuration gives stable
results when the same task is executed repeatedly.

These uncertainty sources remain separate throughout the analysis.

## Frozen formal task subset

The formal confirmatory subset is frozen in `data/stage2/task_subset.csv`.

- SWE-bench Verified universe: 500 tasks.
- Formal Stage 2 subset: **120 tasks**.
- Representative component: **80 tasks**, sampled proportionally by repository.
- High-disagreement enrichment: **40 additional tasks** sampled from tasks with
  Stage 1 disagreement >= 0.90.
- Selection seed: **20260921**.
- The generated subset contains **58/120** tasks with Stage 1 disagreement >= 0.90
  because the representative component also contains high-disagreement tasks.

The deterministic selection implementation is in `src/benchtrust/stage2.py`.
No task may be added or removed based on Stage 2 outcomes.

## Frozen replicate count

The candidate replicate counts were 3, 5, 7, and 10. The pre-registered precision
gate is defined in `configs/stage2.yaml`; design results are published in
`artifacts/stage2_design/replicate_design.csv`.

The frozen formal replicate count is **10 valid repeated executions per system-task cell**.

Under the primary moderate-stochasticity design scenario:

| Replicates | Score p95 abs. error | Run-SD median rel. error | Paired-diff CI half-width | Unstable detection | Rank-reversal abs. error | Gate |
|---:|---:|---:|---:|---:|---:|:---:|
| 3 | 0.036 | 0.350 | 0.095 | 0.595 | 0.232 | no |
| 5 | 0.028 | 0.247 | 0.053 | 0.794 | 0.168 | no |
| 7 | 0.024 | 0.201 | 0.041 | 0.887 | 0.089 | no |
| 10 | 0.021 | 0.161 | 0.032 | 0.952 | 0.068 | yes |

Seven replicates are close, but the paired-difference CI half-width of 0.041 is above
the frozen 0.040 threshold. The threshold is not relaxed after seeing the simulation.

## Non-confirmatory pilot gate

Environment and adapter validation must not consume or tune against the 120 formal
tasks. `data/stage2/pilot_task_subset.csv` is generated deterministically from the
remaining SWE-bench Verified tasks and is guaranteed not to overlap the formal subset.

Pilot design:

- **12 pilot tasks**.
- **2 pilot repetitions** per candidate system-task cell.
- Pilot seed: **20260922**.
- Pilot results are excluded from all confirmatory Stage 2 analyses.

Pilot system-selection criteria are limited to:

- model-adapter compatibility;
- infrastructure/provider failure rate;
- runtime;
- projected cost.

Pilot solve rate, pilot ranking, or any performance-based comparison is forbidden as a
criterion for keeping or dropping a candidate system.

## Candidate system freeze

Stage 2 is designed around **three candidate scaffolds using one common model** so that
scaffold-level reliability can be studied without intentionally changing the base model
between systems.

The candidate definitions live in `configs/stage2_systems.yaml`. They are not yet
formal systems. A candidate becomes frozen only after the pilot confirms it can run and
all reproducibility fields are filled.

Required fields before freeze:

- scaffold repository and exact commit;
- exact model/provider identifier;
- prompt or prompt-template hash;
- tool configuration hash;
- benchmark harness commit;
- container image digest;
- reasoning/decoding settings;
- timeout policy;
- retry policy;
- environment identifier.

Two executions count as replicates only when all reproducibility-relevant fields match.

## Experimental unit and blocking

- Primary experimental unit: one **system × task × replicate** execution.
- Task is a blocking factor shared across systems.
- System comparisons preserve task pairing.
- Independent seeds are used when the runtime exposes a seed.
- Execution order is randomized using a frozen seed to reduce temporal/provider drift confounding.

## Primary outcome

- `resolved = 1` when the official SWE-bench evaluation passes.
- `resolved = 0` for a completed valid agent attempt that fails the task.
- Infrastructure failures are not silently converted to agent failures.

Explicit infrastructure statuses include `infra_error`, `provider_error`, `timeout`,
`harness_error`, and `invalid_artifact`.

The confirmatory analysis excludes executions that never constitute a valid agent
attempt. A separately labeled conservative sensitivity analysis may count selected
non-agent failures as unresolved when scientifically defensible.

## Confirmatory analyses

### A. Run-to-run score variability

For each system, report the replicated benchmark-score distribution, mean, standard
deviation, 95% interval, minimum, and maximum.

### B. Task-level instability

For each system-task cell, estimate empirical solve probability and binary entropy, then
apply pre-registered stable-success, stable-failure, and unstable classifications.

### C. Pairwise replicated comparison

For each system pair, preserve task pairing and report paired differences, intervals,
ordering-reversal frequency, and the probability that a single observed run gives the
opposite ordering from the replicated mean ordering.

### D. Single-run reliability

Report expected absolute deviation of a single-run score from the replicated mean, the
95th percentile absolute deviation, and near-tie ordering-swap frequency.

## Multiple comparisons

Confirmatory pairwise comparisons use Holm adjustment. Unadjusted descriptive intervals
may also be published when clearly labeled.

## Missingness and stop rule

Every missing run must have a reason. Missing outcomes are not imputed in the primary
analysis.

Replicates must not be added or removed after inspecting significance or leaderboard
ordering. If execution stops for an external budget/provider/infrastructure reason, the
reason and frozen completed subset must be documented.

## Stage 2 entry gate

- [x] Stage 1 workflow completed successfully.
- [x] Stage 1 frozen artifacts published.
- [x] Deterministic formal task subset committed.
- [x] Replicate-count simulation committed and **10 replicates** frozen.
- [x] Non-confirmatory pilot task policy defined.
- [ ] Pilot compatibility/cost gate completed.
- [ ] Exact system configurations fully frozen.
- [ ] Protocol status promoted from **PARTIALLY FROZEN** to **FROZEN**.

Formal controlled compute must not begin until every entry-gate item is checked.
