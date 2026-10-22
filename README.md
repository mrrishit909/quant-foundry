# Quant Foundry

An adversarial research lab for algorithmic trading strategies. It runs deterministic,
walk-forward backtests on **synthetic** markets, seals a final holdout before any strategy sees
it, charges explicit costs, records every experiment, and publishes rejections as prominently as
any success. Historical simulation only: no brokerage, no orders, no profit claims.

- **Live site:** https://mrrishit909.github.io/quant-foundry/
- **Current release record:** [`releases/current.json` on the state branch](https://github.com/mrrishit909/quant-foundry/blob/state/releases/current.json)
- **Run records and results:** the [`state` branch](https://github.com/mrrishit909/quant-foundry/tree/state)

## What it does

| Part | Where |
|---|---|
| Synthetic market generator, bounded CSV ingestion, validation | `src/quantfoundry/data/` |
| Strategy registry (trend, mean reversion, volatility breakout) | `src/quantfoundry/strategies/` |
| Event-driven simulator and accounting (close signal, next-open fill, fees, slippage, limits) | `src/quantfoundry/sim/` |
| Walk-forward selection, sealed holdout, sensitivity, benchmarks, verdicts, report | `src/quantfoundry/research/` |
| GitHub-native harness: intake, admission, publication, reconciler, outcome loop, memory | `harness/` |
| Static site (React, Vite, TypeScript), embeddable | `frontend/` |
| Workflows | `.github/workflows/` |

## Use it

- Browse results anonymously on the live site, including the in-browser cost sensitivity.
- Request a run: open the *Research run request* issue form. The owner's requests run
  automatically; anyone else's wait for the owner's `job:approved` label. See
  [docs/OPERATIONS.md](docs/OPERATIONS.md).
- Locally (optional): `uv sync --frozen && uv run python -m quantfoundry run --request req.json --out out/`.

## Documents

[Architecture](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md),
[state model](docs/STATE_MODEL.md), [security](docs/SECURITY.md),
[cost limits](docs/COST_LIMITS.md), [verification](docs/VERIFICATION.md),
[portfolio integration](docs/PORTFOLIO_INTEGRATION.md), [design contract](docs/DESIGN_CONTRACT.md),
[portfolio manifest](portfolio-manifest.json).

## Assets and licences

| Font | Package | Licence |
|---|---|---|
| Newsreader | `@fontsource-variable/newsreader` 5.3.0 | SIL Open Font License 1.1, (c) The Newsreader Project Authors |
| IBM Plex Sans Condensed | `@fontsource/ibm-plex-sans-condensed` 5.3.0 | SIL Open Font License 1.1, (c) IBM Corp. |

The fonts are installed from npm (Fontsource packages, which carry the OFL text) and bundled into the
site's build; nothing loads from a third-party font service. Icons and illustrations are original inline
SVG and CSS; there are no photographs or third-party images. Price series are synthetic, generated from a committed seed; nothing is market data. The code is published
in this public repository.

## Limitations

Synthetic data with a Monday to Friday calendar and no holidays, corporate actions or market
impact beyond a fixed slippage; long only; three strategy families with small grids; daily bars,
so Sharpe estimates are noisy: the t-statistic rule cut false acceptances on pure random walks sharply (1 of 30 default-size runs accepted a strategy in the adversarial check) but does not remove them. Replay was checked across platforms for one request (macOS and
GitHub's Ubuntu runner): every analytic output was byte-identical; `dataset.csv.gz` differed only
in its gzip container (zlib builds differ) while its decompressed content matched the sha256 in
`manifest.json`. Same-machine byte-identical replay is a release gate. The optional AI grader runs only if the owner adds
an inference secret; release records state whether it ran.
