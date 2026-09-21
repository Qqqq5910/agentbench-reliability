# Stage 2 design snapshot

- Frozen task subset: **120** tasks.
- Representative component: **80** tasks.
- High-disagreement enrichment: **40** tasks.
- Selected tasks with Stage 1 disagreement at or above the enrichment threshold: **58/120**.
- Selection seed: **20260921**.
- Primary replicate-design scenario: **moderate**.
- Recommended replicate count: **10**.

## Primary-scenario precision table

| replicates | score p95 abs error | run-SD median rel. error | paired-diff CI half-width | unstable detection | rank-reversal abs error | meets gate |
|---:|---:|---:|---:|---:|---:|:---:|
| 3 | 0.036 | 0.350 | 0.095 | 0.595 | 0.232 | no |
| 5 | 0.028 | 0.247 | 0.053 | 0.794 | 0.168 | no |
| 7 | 0.024 | 0.201 | 0.041 | 0.887 | 0.089 | no |
| 10 | 0.021 | 0.161 | 0.032 | 0.952 | 0.068 | yes |

## Interpretation boundary

This is a design simulation, not evidence of observed within-system rerun stochasticity. Stage 1 cross-system solve rates are used only to preserve a realistic task-difficulty shape. Actual run-to-run stochasticity will be estimated only after controlled Stage 2 repetitions are collected.
