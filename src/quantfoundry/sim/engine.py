"""Day-by-day long-only portfolio simulator.

Rules (also written to assumptions.json):
- The desired state at the close of day t (from `states[t]`) drives orders that fill at the
  open of day t+1. For a backtest over [start, end], the state at the close of start-1 (a bar
  before the window, i.e. warm-up data) drives the first open of the window.
- Orders are sized at the signal close: target shares = floor(w * equity_t / close_t), with
  w = min(1 / number of long symbols, max_weight). Gross exposure therefore stays <= 1.
- Targets are recomputed only when the set of long symbols changes. Entries and exits always
  execute; a symbol that stays long is resized only if its share count is off target by more
  than REBALANCE_BAND (10%), which avoids tiny drift-correction trades.
- Fills: buys at open * (1 + slippage), sells at open * (1 - slippage). Fee = fee_rate *
  |notional|, paid in cash. Sells execute before buys. Whole shares only; a buy that cash
  cannot cover (including its fee) is reduced to what cash covers. No leverage, cash earns 0.
- Missing bar: the symbol cannot trade that day. Its order stays pending and executes at the
  next valid open (unless a newer target replaces it). It is marked at its last valid close.
  Every missing bar inside the span is recorded in `missing_events`.
- Equity is marked at every close.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantfoundry.data.panel import Panel

REBALANCE_BAND = 0.10


@dataclass(frozen=True)
class Costs:
    fee_bps: float = 0.0
    slippage_bps: float = 0.0


@dataclass
class Backtest:
    symbols: tuple[str, ...]
    start: int
    dates: list[str]
    equity: np.ndarray
    cash: np.ndarray
    market_value: np.ndarray
    marks: np.ndarray  # (span, symbols) last valid close; 0 before a symbol's first bar
    trades: list[dict]
    missing_events: list[dict]
    initial_cash: float


def _orders(long_set: np.ndarray, equity: float, marks: np.ndarray, max_weight: float, qty: np.ndarray) -> dict:
    k = int(long_set.sum())
    weight = min(1.0 / k, max_weight) if k else 0.0
    orders = {}
    for j in range(len(qty)):
        target = int(weight * equity // marks[j]) if long_set[j] and marks[j] > 0 else 0
        stays_long = target > 0 and qty[j] > 0
        if target != qty[j] and not (stays_long and abs(target - qty[j]) <= REBALANCE_BAND * target):
            orders[j] = target
    return orders


def backtest(
    panel: Panel,
    states: np.ndarray,
    start: int,
    end: int,
    costs: Costs,
    *,
    max_weight: float = 0.25,
    initial_cash: float = 100_000.0,
) -> Backtest:
    if not 0 <= start <= end < panel.n_days:
        raise ValueError(f"bad span [{start}, {end}] for {panel.n_days} days")
    fee_rate = costs.fee_bps / 1e4
    slip = costs.slippage_bps / 1e4
    valid = panel.valid[: end + 1]
    opens = panel.open
    marks = pd.DataFrame(np.where(valid, panel.close[: end + 1], np.nan)).ffill().fillna(0.0).to_numpy()

    n = panel.n_symbols
    qty = np.zeros(n, dtype=np.int64)
    cash = float(initial_cash)
    long_set = np.zeros(n, dtype=bool)
    pending: dict[int, int] = {}
    if start > 0:
        long_set = states[start - 1].copy()
        pending = _orders(long_set, cash, marks[start - 1], max_weight, qty)

    span = end - start + 1
    equity_out, cash_out, mv_out = np.empty(span), np.empty(span), np.empty(span)
    trades: list[dict] = []
    missing: list[dict] = []
    for t in range(start, end + 1):
        date = panel.day(t)
        # Sells first so their proceeds can fund buys at the same open.
        for j in sorted(pending, key=lambda j: (pending[j] > qty[j], j)):
            if not valid[t, j]:
                continue  # deferred to the next valid open
            ref = float(opens[t, j])
            delta = pending.pop(j) - int(qty[j])
            if delta < 0:
                q = -delta
                fill = ref * (1.0 - slip)
            else:
                fill = ref * (1.0 + slip)
                q = min(delta, int(cash // (fill * (1.0 + fee_rate))))
                while q > 0 and q * fill + q * fill * fee_rate > cash:
                    q -= 1  # guards the float edge of the floor division above
                if q <= 0:
                    continue
            notional = q * fill
            fee = notional * fee_rate
            if delta < 0:
                cash += notional - fee
                qty[j] -= q
            else:
                cash -= notional + fee
                qty[j] += q
            trades.append(
                {
                    "day": t,
                    "date": date,
                    "symbol": panel.symbols[j],
                    "side": "sell" if delta < 0 else "buy",
                    "qty": q,
                    "ref_open": ref,
                    "fill_price": fill,
                    "fee": fee,
                    "slippage_cost": abs(fill - ref) * q,
                    "notional": notional,
                }
            )
        for j in np.flatnonzero(~valid[t]):
            missing.append(
                {
                    "date": date,
                    "symbol": panel.symbols[j],
                    "held_qty": int(qty[j]),
                    "order_deferred": bool(j in pending),
                }
            )

        mv = float(qty @ marks[t])
        equity = cash + mv
        i = t - start
        equity_out[i], cash_out[i], mv_out[i] = equity, cash, mv

        if t < end and not np.array_equal(states[t], long_set):
            long_set = states[t].copy()
            pending = _orders(long_set, equity, marks[t], max_weight, qty)

    return Backtest(
        symbols=panel.symbols,
        start=start,
        dates=[panel.day(t) for t in range(start, end + 1)],
        equity=equity_out,
        cash=cash_out,
        market_value=mv_out,
        marks=marks[start : end + 1],
        trades=trades,
        missing_events=missing,
        initial_cash=float(initial_cash),
    )


def reconcile(bt: Backtest) -> float:
    """Replay the trade ledger independently and return the max absolute accounting error.

    Checks, every day, that cash and cash + sum(qty * mark) rebuilt from the ledger match the
    engine's daily ledger, and at the end that
    equity == initial cash + realized P&L + unrealized P&L - fees (average-cost basis).
    """
    by_day: dict[int, list[dict]] = {}
    for tr in bt.trades:
        by_day.setdefault(tr["day"], []).append(tr)
    index = {s: j for j, s in enumerate(bt.symbols)}
    n = len(bt.symbols)
    cash = bt.initial_cash
    qty = np.zeros(n)
    avg_cost = np.zeros(n)
    realized = 0.0
    fees = 0.0
    err = 0.0
    for i in range(len(bt.equity)):
        for tr in by_day.get(bt.start + i, []):
            j, q, fill = index[tr["symbol"]], tr["qty"], tr["fill_price"]
            if tr["side"] == "buy":
                avg_cost[j] = (avg_cost[j] * qty[j] + q * fill) / (qty[j] + q)
                qty[j] += q
                cash -= q * fill + tr["fee"]
            else:
                realized += q * (fill - avg_cost[j])
                qty[j] -= q
                cash += q * fill - tr["fee"]
            fees += tr["fee"]
        equity = cash + float(qty @ bt.marks[i])
        err = max(err, abs(cash - bt.cash[i]), abs(equity - bt.equity[i]))
    unrealized = float(qty @ (bt.marks[-1] - avg_cost))
    err = max(err, abs(bt.initial_cash + realized + unrealized - fees - bt.equity[-1]))
    return err
