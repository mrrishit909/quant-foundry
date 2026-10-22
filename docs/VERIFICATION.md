# Verification

**The single current release record is `releases/current.json` on the `state` branch.** It is
written only by the Outcome Verification Loop and only when every hard gate passed. Every attempt,
including blocked ones, is in `releases/history.json`, with findings and small evidence files in
`outcomes/<release_id>/`. This document explains the checks; it does not restate their status.

## Hard gates (objective; rubric locked by `rubric/rubric.lock`)

| Gate | What it proves | How |
|---|---|---|
| research-gates | accounting reconciles; known synthetic scenarios behave as expected; future data cannot change earlier decisions; same request gives byte-identical outputs; costs always charged; every experiment recorded; rejected strategies stay visible; holdout sealed and evaluated once | `pytest -m gate tests/quantfoundry` (8 tests) |
| harness | state machine, idempotency, duplicate detection, compare-and-swap concurrency, immutability, intake authorization by identity, injection-safe parsing, ceilings, repair-round bounds, memory guard | `pytest tests/harness` |
| secret-scan | no credential patterns in tracked files or in the live site's HTML, JS and CSS | `scripts/secret_scan.py --live` |
| live-site | the Pages URL serves the app and its snapshot points at the state branch's latest run | HTTP checks |
| published-matches-state | every published result file of the latest run is byte-identical to the state branch | `python -m harness verify-published` |
| browser | 9 checks x 3 widths (390, 768, 1440) against the live site: report, deep links, ledger filters and pagination, parameter explorer, legend and keyboard crosshair, disclosures, cost sliders, navigation state and back button, skip link and focus, reduced motion, loading / empty / error-retry / stale states, compare view; axe (WCAG 2.2 AA serious and critical), horizontal overflow, console errors and failed same-origin requests | Playwright, `frontend/tests/e2e/site.spec.ts` |

## Subjective review (separate from gates)

The rubric's subjective criteria (hierarchy, typography, spacing, palette, motion, responsive
adaptation, distinctiveness, fidelity to `docs/DESIGN_CONTRACT.md`) are scored by an independent
grader only when the repository has an inference secret; otherwise the release record says the
grader did not run. Scores never change a gate result. Screenshots from every outcome run are kept
as Actions artifacts for 14 days and a small representative set is committed with the release
evidence.

## Repairs

A failing gate opens or updates one `type:repair` issue per gate. The same failing set on a new
commit counts as another repair round; after three rounds the release is marked blocked for human
review and its evidence is kept.

## Reproduce locally (optional)

```sh
uv sync --frozen && uv run pytest
cd frontend && npm ci && npm run build && npx playwright install chromium && npm run e2e
```
