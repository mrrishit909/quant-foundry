# Operations

All commands assume the GitHub CLI signed in as the repository owner. Nothing needs a local
clone: every operation is a workflow or an API call.

## Request a run

- **As the owner, from GitHub:** open an issue with the *Research run request* form. Intake
  validates it and dispatches `run.yml`; the issue moves `job:requested -> job:running ->
  job:completed` (or `job:failed` / `job:blocked`) with links to the run record and the site.
- **As the owner, directly:**
  ```sh
  gh workflow run run.yml -R mrrishit909/quant-foundry -f source_type=manual \
    -f request='{"dataset":{"kind":"synthetic","seed":7,"symbols":6,"days":1512,"regime_mix":"balanced"},"strategies":["trend","meanrev","breakout"],"costs":{"fee_bps":1.0,"slippage_bps":5.0},"walk_forward":{"train_days":504,"test_days":126},"holdout_fraction":0.2,"allow_short":false}'
  ```
- **Anyone else:** open the same form. It is labelled `job:blocked` until the owner reviews it
  and adds `job:approved`.

Identical parameters are one request: a repeat links to the existing run instead of computing
again. A failed request can be retried (new attempt, max 3) by submitting it again.

## What each workflow does

| Workflow | Trigger | Effect |
|---|---|---|
| `ci.yml` | push, pull request | lint, harness tests, research gates, frontend build, browser checks on a real fixture snapshot |
| `intake.yml` | issue opened/edited/labelled | validate + authorize + dispatch `run.yml` |
| `run.yml` | dispatch | admit -> compute -> publish -> Pages -> Outcome Verification Loop -> memory proposals |
| `pages.yml` | push to main, called by `run.yml` | snapshot + build + deploy + live smoke check |
| `outcome.yml` | called by `run.yml`, manual | hard gates, live browser evidence, optional grader, release record |
| `memory.yml` | called by `run.yml`, manual, `memory:accept` label | propose lessons / accept owner-approved lessons |
| `operations.yml` | daily, weekly, manual | reconcile, weekly refresh run, bootstrap |

## Routine checks

```sh
gh run list -R mrrishit909/quant-foundry --limit 10
gh api repos/mrrishit909/quant-foundry/contents/releases/current.json?ref=state --jq .content | base64 -d
gh issue list -R mrrishit909/quant-foundry --label type:repair
```

## Recover

- Stuck or interrupted runs: `gh workflow run operations.yml -f task=reconcile`.
- Recreate labels or a missing state branch: `gh workflow run operations.yml -f task=bootstrap`.
- Re-deploy the site from current state: `gh workflow run pages.yml`.
- Re-verify the live release: `gh workflow run outcome.yml`.

## Accept memory

Review the open `type:memory` issue. Add the `memory:accept` label to merge its proposals into
`memory/lessons.json`; close it without the label to reject them.

## Enable the optional grader (owner action)

Add one repository secret: `ANTHROPIC_API_KEY`, or `CLAUDE_CODE_OAUTH_TOKEN` generated with
`claude setup-token`. Without it the grader is skipped and release records say
"inference credentials are not configured".

## Squash the state branch (only if it nears 500 MB)

Export `index.json`, `latest.json`, `requests/`, `holdout/`, `releases/` and the retained run
directories, create a new orphan commit with them, and push it as `state` after confirming no
run is in progress. This is a manual owner action; no workflow rewrites history.
