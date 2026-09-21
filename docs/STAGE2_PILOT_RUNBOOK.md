# Stage 2 pilot execution runbook

The pilot executor is intentionally safe-by-default. Merely merging code, running CI,
or invoking the command with no flags cannot call a paid model.

## Safety gates

The default command is a dry run:

```bash
benchtrust stage2-pilot-run
```

It reads the frozen command plan, selects the requested rows, and writes execution
status with `status=dry_run`. It does not invoke any scaffold command.

A real pilot cell requires **both** explicit flags:

```bash
benchtrust stage2-pilot-run \
  --execute \
  --accept-api-costs \
  --limit 1
```

If `--execute` is present without `--accept-api-costs`, the command exits before
starting any model call.

## Recommended sequence

1. Run the no-call preflight workflow and require green CI.
2. Dry-run the entire 72-row plan.
3. Execute exactly one cell with `--limit 1`.
4. Inspect only adapter/infrastructure behavior, runtime, and projected cost.
5. Do **not** use solve success or pilot ranking to keep/drop a candidate.
6. Only after the one-cell smoke test is operationally valid, continue through the
   frozen 72-row pilot order.

## Execution controls

Use `--system-id` to restrict to one candidate, `--start-order` to resume at a
specific frozen order position, and `--limit` to cap how many cells are selected.

Completed cells are skipped unless `--redo` is explicitly supplied.

The executor writes per-run stdout, stderr, and metadata under
`artifacts/stage2_pilot/runs/...` plus a normalized
`artifacts/stage2_pilot/execution_status.csv`.

## Required credentials

SWE-agent and mini-swe-agent require `OPENAI_API_KEY`. Moatless currently declares
`OPENAI_API_KEY` and `VOYAGE_API_KEY`. All required secrets are checked for the
entire selected slice before the first command is launched.

No credential values are written to artifacts.


## Isolated runtimes

Each candidate scaffold uses its own virtual environment under
`.benchtrust/stage2/venvs/<system_id>`. This prevents dependency versions from one
agent from changing another agent's runtime.

Preview the setup with no installation:

```bash
benchtrust stage2-pilot-setup
```

Create the isolated environments only when you want to prepare the machine:

```bash
benchtrust stage2-pilot-setup --install
```

The setup command does not invoke a language model. It verifies each pinned checkout,
installs that scaffold into its own venv, and runs only the scaffold's `--help` smoke
command. Real pilot execution refuses to start when the matching isolated runtime has
not been prepared.
