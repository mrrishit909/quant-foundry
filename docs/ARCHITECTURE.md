# Architecture

```
 GitHub Issue (form)          workflow_dispatch / weekly schedule
        |                                  |
   intake.yml  -- validate, authorize -->  run.yml
                                           |
          admit (state: running|blocked, idempotency, ceilings)
                                           |
          compute (read-only token, no secrets): python -m quantfoundry run
                                           |  artifact run-<run_id> (14 days)
          publish (validate outputs, immutable runs/<run_id>/, latest.json)
                                           |
          pages.yml (workflow_call): snapshot state -> build -> deploy -> smoke
                                           |
          outcome.yml: hard gates + live browser evidence + optional grader -> release record
                                           |
          memory.yml: deterministic lesson proposals -> type:memory issue
```

## Components

- **Engine (`src/quantfoundry`)**: pure, deterministic Python (numpy, pandas). Given a validated
  request it writes a fixed set of files (see `quantfoundry/outputs.py` for the contract). Signals use
  bars up to the close of day t; orders fill at the open of day t+1 with adverse slippage and a
  proportional fee; whole shares; long only; position cap 25 % per symbol; cash earns nothing.
  Every walk-forward window starts flat with 100,000 and is warmed up on earlier bars. The last
  `holdout_fraction` of dates is sealed until parameters are frozen.
- **Harness (`harness/`)**: stdlib plus `jsonschema`. `issueform` parses untrusted issue forms;
  `intake` authorizes by identity; `runs` admits and publishes; `state` implements optimistic
  compare-and-swap writes to the `state` branch; `reconcile` repairs interrupted runs;
  `snapshot` builds the site's data; `outcome` and `memory` are the verification and curation
  loops. Project-specific behaviour lives in `project_hooks.py` (output validation, request
  feasibility, cross-run holdout audit, memory candidates).
- **Site (`frontend/`)**: React 19 + Vite + TypeScript, no UI or chart library. Reads only the
  published snapshot; computes the cost what-if in memory; never stores state in the browser.
  Hash routing for deep links on Pages; `QuantFoundryApp` and `mount()` are exported for embedding.

## Decisions

| Decision | Why |
|---|---|
| State on a dedicated branch, not in Issues | Issues are a human ledger; structured data needs files, history and atomic multi-file commits |
| Compare-and-swap push + re-applied mutations | Concurrency groups alone can cancel pending runs; the push rejection is the real guard |
| Reusable workflows for chaining | Events created with `GITHUB_TOKEN` do not start other workflows (dispatch excepted) |
| Synthetic data only | Redistribution of real market data could not be verified as free; synthetic data is reproducible and honest about scope |
| Deterministic engine, LLM only for optional grading | Parameter searches and accounting must be reproducible and free |
| Hand-built SVG charts | Small bundle, exact control of dash patterns, labels and the sealed-holdout band |

## Data contracts

`schemas/request.schema.json` (run parameters), `schemas/run.schema.json` (run record),
`schemas/release.schema.json`, `schemas/memory.schema.json`, `schemas/grader.schema.json`.
