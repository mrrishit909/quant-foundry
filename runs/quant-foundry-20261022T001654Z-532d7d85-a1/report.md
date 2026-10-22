# Quant Foundry research report

Historical backtest on SYNTHETIC data. No brokerage, no live orders, no profit claims.

## Summary

All 3 strategies were rejected on this synthetic dataset: no strategy cleared every out-of-sample, benchmark, holdout, stability and trade-count check.

## Dataset

- Synthetic, seed 12, 8 symbols, 2016 days, regime mix `choppy`
- Span 2015-01-02 to 2022-09-23, 16128 rows, sha256 `4f154f7d58ada7840779ba09c20610d061a3d2eb1a0a6cfe5de8715ab930cb88`
- Calendar: synthetic business days: pandas.bdate_range starting 2015-01-02, Monday to Friday, no exchange holidays
- Injected defects: 3 missing bar(s): SYN06 2017-07-19, SYN06 2018-04-13, SYN06 2020-11-24
- Data quality status: warn (schema=pass, sorted_dates=pass, duplicate_rows=pass, ohlc_consistency=pass, positive_prices=pass, non_negative_volume=pass, missing_bars=warn, large_moves=pass, calendar_coverage=pass)
- Input manifest hash: `sha256:063da67de9e25b7e63f4a2e67c9fafb9a657a6a4c9158a23ea6aa38f60ad1a33`

## Protocol

- Sealed holdout: 2020-10-20 to 2022-09-23 (last 25.00% of dates, rounded down)
- Rolling walk-forward on the development period: 6 windows of 504 train / 126 test days, step 126, after a 200-bar warm-up prefix
- Selection: best in-sample Sharpe over the full grid (ties: fewer trades, then lexicographic params)
- Final params frozen from the last window, then the holdout is evaluated once per strategy
- Costs: fee 1.0 bps, slippage 5.0 bps
- Acceptance needs all of: OOS Sharpe > 0.30, OOS Sharpe > buy-and-hold OOS Sharpe, holdout return > 0, parameter stability >= 0.30, at least 10 OOS trades

## Assumptions

- **calendar**: Synthetic Monday to Friday business days from 2015-01-02 with no exchange holidays.
- **cash**: Each backtest starts with 100,000 in cash. Cash earns 0. No leverage: a buy that cash cannot cover (including its fee) is reduced to the whole shares cash covers.
- **equity_chaining**: equity.csv shows the chained OOS curve and then continues into the holdout by chaining holdout returns onto the last OOS value. Dates between the last OOS window and the holdout start (if any) are not part of either curve.
- **fees**: Fee = 1.0 bps of absolute traded notional, paid in cash on every fill.
- **fill_timing**: Orders fill at the open of the next bar (t+1). A window's first open is driven by the state at the close of the bar before the window.
- **holdout_split**: The last floor(days * holdout_fraction) dates are the sealed holdout, evaluated once per strategy with parameters frozen from the last walk-forward window.
- **metrics**: Daily simple returns; 252 trading days per year; Sharpe = mean / std (ddof=1) * sqrt(252) with rf = 0 and 0.0 for a flat curve; max_drawdown is a negative fraction; turnover = sum of daily traded notional / previous close equity; exposure = mean gross weight at the close; stitched fees and slippage are summed over segments, each run on the initial cash.
- **missing_data**: A missing bar (NaN) cannot be traded: its order is deferred to the symbol's next valid open, the position is marked at the last valid close, and each such day is recorded in checks.json. Signals are computed on the symbol's valid bars only and the last state is carried across the gap.
- **position_limits**: Equal weight among symbols currently long, capped at 0.25 per symbol, so gross exposure is at most 1.0. Targets are sized at the signal close: floor(weight * equity / close).
- **rebalance**: Targets are recomputed only when the set of long symbols changes. Entries and exits always execute; a symbol that stays long is resized to the new equal weight only if its share count is more than 10% off target. No calendar rebalancing. Sells execute before buys at the same open.
- **share_rounding**: Whole shares only, rounded down.
- **shorting**: Short selling is not supported; allow_short must be false.
- **signal_timing**: computed from bars up to and including the close of day t; the resulting order fills at the open of day t+1
- **slippage**: Fixed adverse slippage of 5.0 bps: buys fill at open * (1 + s), sells at open * (1 - s). It is embedded in fill prices and also reported separately as sum(|fill - open| * qty). No other market impact is modelled.
- **warmup**: The first 200 development bars (the largest warm-up in the registry) are never evaluated; they prime indicators. Each backtest computes signals from all bars before its start, never from bars after it. A strategy is flat until its own warm-up is complete.
- **window_boundaries**: Each walk-forward backtest starts flat with the initial cash. Positions open at a window's end are marked at that close and not charged an exit; the next window starts flat, so a position held across a boundary pays entry costs again. OOS segments are contiguous and chained by returns.

## Results

| Strategy | Verdict | OOS Sharpe | OOS return | OOS max DD | OOS trades | Holdout return | Stability | Frozen params |
|---|---|---|---|---|---|---|---|---|
| trend | rejected | -0.42 | -13.46% | -27.85% | 320 | -28.00% | 0.33 | `{"fast":40,"slow":200}` |
| meanrev | rejected | 2.16 | 103.32% | -12.08% | 334 | 12.68% | 0.22 | `{"entry_z":1.0,"lookback":40}` |
| breakout | rejected | 0.81 | 8.42% | -5.82% | 13 | -10.44% | 0.11 | `{"N":100,"k":1.0}` |
| buy-and-hold (benchmark) | n/a | 0.16 | 3.20% | -11.90% | 8 | -15.61% | n/a | n/a |
| cash (benchmark) | n/a | 0.00 | 0.00% | 0.00% | 0 | 0.00% | n/a | n/a |

OOS span 2017-09-14 to 2020-08-06.

## Rejections

- **trend**
  - OOS Sharpe -0.42 does not clear the 0.30 bar
  - OOS Sharpe -0.42 does not beat buy-and-hold OOS Sharpe 0.16
  - Holdout total return -28.00% is not positive
- **meanrev**
  - Parameter stability 0.22 is below the 0.30 bar (2 of 9 combos within 0.5 Sharpe of the best)
- **breakout**
  - Holdout total return -10.44% is not positive
  - Parameter stability 0.11 is below the 0.30 bar (1 of 9 combos within 0.5 Sharpe of the best)

## Self checks

- Accounting: max reconciliation error 2.04e-10 over 329 backtests (tolerance 1e-6): passed
- Lookahead probe at cutoff 2022-04-28: passed
- Holdout evaluated exactly once per strategy: yes
- Missing-bar events in recorded backtests: 6

## Limitations

- Synthetic data only: regimes, jumps and defects are generated, so no result transfers to real markets.
- No exchange holidays, no corporate actions (splits, dividends), no delistings or survivorship effects.
- Long-only, no leverage, cash earns nothing.
- Signals at the close fill at the next open; no intraday execution, no partial fills.
- Market impact is a fixed slippage in bps; no spread or volume-dependent impact model.
- A small parameter grid and few walk-forward windows; a high Sharpe here can still be luck.
