# Stage 2 system-selection gate

The formal Stage 2 systems are **not frozen yet**. This document records the candidate
set and the rules that must be satisfied before controlled repeated runs can begin.

## Why not rerun the Stage 1 leaderboard top three?

Stage 1 analyzes a frozen historical public leaderboard. That does not imply those
historical submissions can be reproduced today with identical private scaffolds,
provider behavior, prompts, or retired model versions.

Stage 2 therefore targets a different estimand: **current controlled run-to-run
reliability under fully frozen, reproducible configurations**.

## Candidate design

Use one common model across three distinct coding-agent scaffolds. Holding the model
constant makes scaffold and execution reliability easier to interpret.

| Candidate | Repository | Frozen candidate commit |
|---|---|---|
| SWE-agent | `SWE-agent/SWE-agent` | `3ea751c087f32b16e039a2233dd6eefecef325d5` |
| OpenHands | `OpenHands/OpenHands` | `a5eb10d584f4dfbc6ac0fd7043c5b73bc0fa9f8e` |
| Moatless | `aorwall/moatless-tools` | `011ead57a5c81664e9c45e07e1f50b17e695cc63` |

Candidate common model: `gpt-5.6-terra`, direct OpenAI provider access,
reasoning effort `medium`. This remains candidate-only until each scaffold's adapter
path is validated in the pilot.

## Pilot gate

The pilot uses `data/stage2/pilot_task_subset.csv`, never the 120 formal tasks.

A candidate may be rejected or repaired only for:

- unsupported model/API adapter behavior;
- excessive infrastructure/provider failure rate;
- operational runtime failure;
- projected cost that makes the frozen 3,600-run formal matrix infeasible.

A candidate may **not** be selected or rejected because its pilot solve rate is high or
low. Pilot outcomes are not part of the confirmatory dataset.

## Formal matrix if all three candidates pass

- 120 formal tasks
- 3 frozen systems
- 10 valid replicates

Total planned formal cells: **3,600 valid system-task executions**.

This count excludes pilot runs and replacement attempts required by pre-defined
infrastructure-failure rules.

## Remaining freeze fields

Before changing `configs/stage2_systems.yaml` to `status: frozen`, record:

1. prompt/template hash;
2. tool configuration hash;
3. benchmark harness commit;
4. container digest;
5. provider API surface actually used;
6. environment identifier;
7. timeout policy;
8. retry policy.

Only after those fields and the pilot gate are complete may
`docs/STAGE2_PROTOCOL.md` be promoted to **FROZEN**.
