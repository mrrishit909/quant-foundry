# Quant Foundry research report

Historical backtest on SYNTHETIC data. No brokerage, no live orders, no profit claims.

## Summary

All 3 strategies were rejected on this synthetic dataset: no strategy cleared every out-of-sample, significance, benchmark, holdout, stability and round-trip check.

## Dataset

- Synthetic, seed 202644, 6 symbols, 1512 days, regime mix `balanced`
- Span 2015-01-02 to 2020-10-19, 9072 rows, sha256 `63065ec63e1d9cd1547abf299ce01a0cf8f0db76b98d801b2920d64cde256d15`
- Calendar: synthetic business days: pandas.bdate_range starting 2015-01-02, Monday to Friday, no exchange holidays
- Injected defects: 2 missing bar(s): SYN06 2017-11-14, SYN06 2018-07-13
- Data quality status: warn (schema=pass, sorted_dates=pass, duplicate_rows=pass, ohlc_consistency=pass, positive_prices=pass, non_negative_volume=pass, missing_bars=warn, large_moves=pass, calendar_coverage=pass)
- Input manifest hash: `sha256:9efab77cf81dea904ba097ed0f2d73d93a3096ca0918a770ade64001a1d72102`

## Protocol

- Sealed holdout: 2019-08-23 to 2020-10-19 (last 20.00% of dates, rounded down)
- Rolling walk-forward on the development period: 4 windows of 504 train / 126 test days, step 126, laid out backward so the last test window ends the day before the holdout; no train window starts before bar 200
- Selection: best in-sample Sharpe over the full grid (ties: fewer trades, then lexicographic params)
- Final params frozen from the window adjacent to the holdout, then the holdout is evaluated once per strategy and liquidated at its final close
- Costs: fee 1.0 bps, slippage 5.0 bps

## Acceptance rules

A strategy is accepted only if ALL hold: (1) OOS Sharpe > 0.3; (2) OOS Sharpe t-statistic = Sharpe * sqrt(OOS days / 252) >= 2.0; (3) OOS Sharpe > buy-and-hold OOS Sharpe; (4) holdout total return after liquidation > 0; (5) parameter stability (share of grid combos with OOS Sharpe within 0.5 of the best) >= 0.3; (6) at least 10 completed OOS round trips (sells that close a position). Rule 2 exists because this run tried 27 grid combos in-sample and the standard error of an annualized Sharpe is about sqrt(252 / days), 0.71 over its 504 OOS days: a Sharpe of 0.3 alone is well inside the noise. A t-statistic of 2.0 is a guard, not a full multiple-comparison correction; noise can still pass occasionally.

## Assumptions

- **calendar**: Synthetic Monday to Friday business days from 2015-01-02 with no exchange holidays.
- **cash**: Each backtest starts with 100,000 in cash. Cash earns 0. No leverage: a buy that cash cannot cover (including its fee) is reduced to the whole shares cash covers.
- **equity_chaining**: equity.csv shows the chained OOS curve and then continues into the holdout by chaining holdout returns onto the last OOS value. The OOS span ends the day before the holdout.
- **fees**: Fee = 1.0 bps of absolute traded notional, paid in cash on every fill.
- **fill_timing**: Orders fill at the open of the next bar (t+1). A window's first open is driven by the state at the close of the bar before the window.
- **holdout_liquidation**: At the end of the holdout every open position is sold at the final close (the last valid close if the final bar is missing) with the same slippage (applied to the close) and fee, so holdout returns are realized. These fills appear in trades.csv with the final close in the ref_open column. The holdout buy-and-hold benchmark is liquidated the same way.
- **holdout_split**: The last floor(days * holdout_fraction) dates are the sealed holdout (exact decimal floor). It is evaluated once per strategy with the parameters chosen in the walk-forward window adjacent to it.
- **metrics**: Daily simple returns; 252 trading days per year; Sharpe = mean / std (ddof=1) * sqrt(252) with rf = 0 and 0.0 for a flat curve; max_drawdown is a negative fraction; turnover = sum of daily traded notional / previous close equity; exposure = mean gross weight at the close; trades counts fills, round_trips counts sells that take a position to zero; days is the number of daily observations; stitched fees and slippage are summed over segments, each run on the initial cash.
- **missing_data**: A missing bar (NaN) cannot be traded: its order is deferred to the symbol's next valid open, the position is marked at the last valid close, and each such day is recorded in checks.json. Signals are computed on the symbol's valid bars only and the last state is carried across the gap.
- **position_limits**: Target weight = min(1 / number of long symbols, 0.25), sized at the signal close as floor(weight * equity / close). Enforced exactly: at every decision (a change in the set of long symbols) no position is left above 0.25 of equity at that close; larger ones are trimmed to target. Not enforced: between decisions positions drift with prices and can exceed 0.25. Gross exposure never exceeds 1.0 because cash cannot go negative.
- **rebalance**: Targets are recomputed only when the set of long symbols changes. Entries and exits always execute; a symbol that stays long is resized to the new equal weight if its share count is more than 10% off target or it is above the 0.25 cap. No calendar rebalancing. Sells execute before buys at the same open.
- **share_rounding**: Whole shares only, rounded down.
- **shorting**: Short selling is not supported; allow_short must be false.
- **signal_timing**: computed from bars up to and including the close of day t; the resulting order fills at the open of day t+1
- **slippage**: Fixed adverse slippage of 5.0 bps: buys fill at open * (1 + s), sells at open * (1 - s). It is embedded in fill prices and also reported separately as sum(|fill - open| * qty). No other market impact is modelled.
- **verdict_rules**: A strategy is accepted only if ALL hold: (1) OOS Sharpe > 0.3; (2) OOS Sharpe t-statistic = Sharpe * sqrt(OOS days / 252) >= 2.0; (3) OOS Sharpe > buy-and-hold OOS Sharpe; (4) holdout total return after liquidation > 0; (5) parameter stability (share of grid combos with OOS Sharpe within 0.5 of the best) >= 0.3; (6) at least 10 completed OOS round trips (sells that close a position). Rule 2 exists because this run tried 27 grid combos in-sample and the standard error of an annualized Sharpe is about sqrt(252 / days), 0.71 over its 504 OOS days: a Sharpe of 0.3 alone is well inside the noise. A t-statistic of 2.0 is a guard, not a full multiple-comparison correction; noise can still pass occasionally.
- **walk_forward_layout**: Windows are laid out backward from the last development day: the last test window ends the day before the holdout, earlier windows step back by test_days, at most 8 windows, and no train window starts before bar 200. Development bars before the first train window are only used as indicator history.
- **warmup**: No train window starts before development bar 200 (the largest warm-up in the registry), so indicators are always primed by earlier bars. Each backtest computes signals from all bars before its start, never from bars after it.
- **window_boundaries**: Each OOS window backtest starts flat with the initial cash. Positions still open at a window's end are marked at that close without an exit cost and are not liquidated; the next window starts flat, so a position a continuous run would have carried pays one extra entry cost (a small conservative penalty), and its round trip only counts once it closes inside a window. OOS segments are contiguous and chained by returns.

## Results

| Strategy | Verdict | OOS Sharpe | OOS t-stat | OOS days | OOS return | OOS max DD | OOS fills | OOS round trips | Holdout return | Stability | Frozen params |
|---|---|---|---|---|---|---|---|---|---|---|---|
| trend | rejected | -0.205 | -0.290 | 504 | -7.60% | -24.09% | 181 | 31 | 23.42% | 0.67 | `{"fast":20,"slow":100}` |
| meanrev | rejected | 0.869 | 1.229 | 504 | 17.63% | -7.39% | 274 | 99 | -6.25% | 0.22 | `{"entry_z":1.5,"lookback":20}` |
| breakout | rejected | -0.483 | -0.683 | 504 | -11.96% | -16.34% | 75 | 20 | 17.96% | 0.56 | `{"N":55,"k":0.0}` |
| buy-and-hold (benchmark) | n/a | 0.921 | n/a | 504 | 28.04% | -12.80% | 6 | n/a | 15.15% | n/a | n/a |
| cash (benchmark) | n/a | 0.000 | n/a | 504 | 0.00% | 0.00% | 0 | n/a | 0.00% | n/a | n/a |

OOS span 2017-09-18 to 2019-08-22.

## Rejections

- **trend**
  - OOS Sharpe -0.205 does not clear the 0.30 bar
  - OOS Sharpe t-statistic -0.290 is below the 2.0 significance bar (504 out-of-sample days)
  - OOS Sharpe -0.205 does not beat buy-and-hold OOS Sharpe 0.921
- **meanrev**
  - OOS Sharpe t-statistic 1.229 is below the 2.0 significance bar (504 out-of-sample days)
  - OOS Sharpe 0.869 does not beat buy-and-hold OOS Sharpe 0.921
  - Holdout total return -6.25% (liquidated at the final close) is not positive
  - Parameter stability 0.22 is below the 0.30 bar (2 of 9 combos within 0.5 Sharpe of the best)
- **breakout**
  - OOS Sharpe -0.483 does not clear the 0.30 bar
  - OOS Sharpe t-statistic -0.683 is below the 2.0 significance bar (504 out-of-sample days)
  - OOS Sharpe -0.483 does not beat buy-and-hold OOS Sharpe 0.921

## Self checks

- Accounting: max reconciliation error 1.75e-10 over 221 backtests (tolerance 1e-6): passed
- Lookahead probe at cutoff 2020-01-03: passed
- Holdout evaluated exactly once per strategy: yes
- Missing-bar events in recorded backtests: 6

## Limitations

- Synthetic data only: regimes, jumps and defects are generated, so no result transfers to real markets.
- No exchange holidays, no corporate actions (splits, dividends), no delistings or survivorship effects.
- Long-only, no leverage, cash earns nothing.
- Signals at the close fill at the next open; no intraday execution, no partial fills.
- Market impact is a fixed slippage in bps; no spread or volume-dependent impact model.
- A small parameter grid and few walk-forward windows; a high Sharpe here can still be luck.
