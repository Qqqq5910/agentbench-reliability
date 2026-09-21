# Stage 2 system-selection gate

The formal Stage 2 systems are **not frozen yet**. The task set and replicate count are
already frozen; this gate only decides whether a candidate scaffold is operationally
reproducible enough to enter the paid pilot.

## Candidate design

Use one common model across three distinct coding-agent scaffolds. The common candidate
model is `gpt-5.6-terra` at reasoning effort `medium` through direct OpenAI credentials.

| Candidate | Repository | Pinned commit |
|---|---|---|
| SWE-agent | `SWE-agent/SWE-agent` | `3ea751c087f32b16e039a2233dd6eefecef325d5` |
| mini-swe-agent | `SWE-agent/mini-swe-agent` | `04d809ceab9df28f9adaed044884180159172930` |
| Moatless | `aorwall/moatless-tools` | `011ead57a5c81664e9c45e07e1f50b17e695cc63` |

## Preflight replacement of OpenHands

OpenHands was initially listed as a candidate. Before any paid pilot call, the pinned
OpenHands repository was inspected for a native SWE-bench execution path. The current
pinned repository no longer contains an in-repo SWE-bench evaluation runner, while the
other candidates expose explicit SWE-bench execution entry points.

OpenHands was therefore replaced by mini-swe-agent **before performance was observed**.
This is an adapter/reproducibility decision permitted by the preregistered pilot gate;
it is not a performance-based selection.

mini-swe-agent is suitable for the replacement because the pinned repository exposes
a first-party `swebench-single` runner, Docker execution, LiteLLM integration, model
kwargs including reasoning effort, and a small auditable agent loop.

## Pilot gate

The pilot uses `data/stage2/pilot_task_subset.csv`, never the 120 formal tasks.
The fixed pilot matrix is 12 tasks × 3 systems × 2 repetitions = **72 planned runs**.

A candidate may be rejected or repaired only for:

- unsupported model/API adapter behavior;
- excessive infrastructure/provider failure rate;
- operational runtime failure;
- projected cost that makes the frozen formal matrix infeasible.

Pilot solve rate and pilot ranking are forbidden selection criteria.

## Credential boundary

SWE-agent and mini-swe-agent require `OPENAI_API_KEY` for the candidate model.
Moatless additionally declares `VOYAGE_API_KEY` in preflight because its SWE-bench
retrieval stack depends on Voyage-backed embeddings. This extra dependency is itself a
valid operational/cost consideration, but no candidate is dropped until the pilot gate
is evaluated under the frozen rules.

## Remaining freeze fields

Before `configs/stage2_systems.yaml` can become `status: frozen`, record prompt/tool
hashes, benchmark harness commit, container digest, provider API surface, environment
identifier, timeout policy, and retry policy for every retained system.
