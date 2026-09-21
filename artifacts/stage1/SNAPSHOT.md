# Stage 1 frozen snapshot

> Generated from the pinned source revisions in `configs/swebench_verified_stage1.yaml`.

## Snapshot facts

- Primary single-attempt submissions: **45**.
- Benchmark tasks in the paired primary analysis: **500**.
- Highest point estimate in this frozen cohort: `20251205_sonar-foundation-agent_claude-opus-4-5` at **79.2%** (task-bootstrap 95% interval **75.6%–82.6%**).
- Second-highest point estimate: `20251215_livesweagent_claude-opus-4-5` at **79.2%** (95% interval **75.6%–82.6%**).
- In paired task bootstrap samples, the first point-estimate system ranks above the second with tie-splitting frequency **0.497**. This is a resampling statistic, not a posterior probability of intrinsic superiority.
- Tasks with normalized cross-system disagreement >= 0.9: **146/500**.
- Reconstructed resolved-count mismatches: **0**; independently reported-score mismatches where metadata were available: **0**.
- For the top point-estimate pair, the first simulated task count reaching >=80% exact-McNemar detection power: **not reached in simulated range**.

## Interpretation boundary

These results quantify **task-sampling uncertainty** for a frozen public leaderboard cohort. They do **not** estimate same-system run-to-run stochasticity. Public submissions are not treated as independent reruns of a frozen agent configuration.

## Generated artifacts

- `leaderboard_bootstrap.csv`
- `pairwise_ordering_probability.csv`
- `task_summary.csv`
- `power_top_pair.csv` and `.png`
- `figures/fig01_score_intervals.png`
- `figures/fig02_rank_intervals.png`
- `figures/fig03_pairwise_ordering.png`
- `figures/fig04_task_disagreement.png`
- `primary_submissions.csv`
- `score_reproduction.csv`
- `provenance.json`
