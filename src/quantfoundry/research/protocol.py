"""Research protocol.

1. Split: the last floor(days * holdout_fraction) dates are the SEALED HOLDOUT; the rest is
   the development period.
2. Rolling walk-forward over the development period after a warm-up prefix: train_days
   in-sample then test_days out-of-sample, step test_days, at most 8 windows.
3. Per strategy and window: every grid combo is backtested in-sample, the best in-sample
   Sharpe is chosen (ties: fewer trades, then lexicographic params) and evaluated OOS.
   Selection only ever receives development data truncated at the window's train end.
4. OOS segments are chained into one OOS curve per strategy.
5. Sensitivity: every grid combo re-run OOS with fixed params over all windows.
6. Final params are frozen as the last window's choice, then the holdout is evaluated
   exactly once per strategy with them.
7. Benchmarks (equal-weight buy-and-hold, cash) over the same OOS and holdout spans, then a
   verdict per strategy with every failing reason.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from quantfoundry.data.panel import Panel
from quantfoundry.research.metrics import TRADING_DAYS, Curve, curve, growth, metrics, stitch
from quantfoundry.sim.engine import REBALANCE_BAND, Backtest, Costs, backtest, reconcile
from quantfoundry.strategies import REGISTRY, SIGNAL_TIMING, Strategy, get_strategy, params_key

INITIAL_CASH = 100_000.0
MAX_WEIGHT = 0.25
MAX_WINDOWS = 8
# Largest warm-up of any registry combo (trend slow=200). No window evaluates on these first
# development bars; they only prime indicators. Every window is therefore warmed up from bars
# strictly before its start, and all strategies share identical windows.
WARMUP_PREFIX = max(s.warmup_bars(p) for s in REGISTRY.values() for p in s.params_grid)
MIN_OOS_SHARPE = 0.3
MIN_STABILITY = 0.3
MIN_TRADES = 10
STABILITY_TOLERANCE = 0.5
ACCOUNTING_TOLERANCE = 1e-6
SHORT_ERROR = "allow_short=true is not supported: Quant Foundry only simulates long-only strategies (no short selling)"


class ProtocolError(ValueError):
    """The request cannot be run under the research protocol."""


class HoldoutLeakError(AssertionError):
    """Parameter selection was handed data from the sealed holdout."""


@dataclass(frozen=True)
class Window:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def holdout_start_index(n_days: int, fraction: float) -> int:
    return n_days - math.floor(n_days * fraction)


def make_windows(n_dev: int, train_days: int, test_days: int) -> list[Window]:
    windows: list[Window] = []
    while len(windows) < MAX_WINDOWS:
        train_start = WARMUP_PREFIX + len(windows) * test_days
        test_start = train_start + train_days
        test_end = test_start + test_days - 1
        if test_end >= n_dev:
            break
        windows.append(Window(len(windows), train_start, test_start - 1, test_start, test_end))
    if not windows:
        need = WARMUP_PREFIX + train_days + test_days
        raise ProtocolError(
            f"the development period has {n_dev} bars but one walk-forward window needs {need} "
            f"({WARMUP_PREFIX} warm-up + {train_days} train + {test_days} test); use more days, "
            "shorter windows or a smaller holdout_fraction"
        )
    return windows


def run_strategy(panel: Panel, spec: Strategy, params: dict, start: int, end: int, costs: Costs) -> Backtest:
    view = panel.upto(end)
    states = spec.states(view, params)
    return backtest(view, states, start, end, costs, max_weight=MAX_WEIGHT, initial_cash=INITIAL_CASH)


def select_params(
    spec: Strategy, panel: Panel, window: Window, costs: Costs, holdout_start
) -> tuple[dict, list[tuple[dict, Backtest, dict]]]:
    """In-sample grid search. `panel` must end before the holdout; this is enforced."""
    if panel.dates[-1] >= holdout_start:
        raise HoldoutLeakError(
            f"selection for {spec.id} saw {panel.dates[-1].date()}, holdout starts {holdout_start.date()}"
        )
    evaluated = []
    for p in spec.params_grid:
        bt = run_strategy(panel, spec, p, window.train_start, window.train_end, costs)
        evaluated.append((p, bt, metrics(curve(bt))))
    best = min(evaluated, key=lambda e: (-round(e[2]["sharpe"], 12), e[2]["trades"], params_key(e[0])))
    return dict(best[0]), evaluated


def evaluate_holdout(spec: Strategy, params: dict, panel: Panel, start: int, costs: Costs) -> Backtest:
    return run_strategy(panel, spec, params, start, panel.n_days - 1, costs)


def buy_and_hold(panel: Panel, start: int, end: int, costs: Costs) -> Backtest:
    """Equal weight 1/n in every symbol bought at the first open, never rebalanced.

    The benchmark is not bound by the strategies' 0.25 per-symbol cap.
    """
    view = panel.upto(end)
    states = np.ones(view.close.shape, dtype=bool)
    return backtest(view, states, start, end, costs, max_weight=1.0 / view.n_symbols, initial_cash=INITIAL_CASH)


def cash_curve(days: int) -> Curve:
    zeros = np.zeros(days)
    return Curve(zeros, zeros, zeros, 0, 0.0, 0.0)


def judge(oos: dict, buyhold_oos: dict, holdout: dict, sens: dict) -> tuple[str, list[str]]:
    reasons = []
    if not oos["sharpe"] > MIN_OOS_SHARPE:
        reasons.append(f"OOS Sharpe {oos['sharpe']:.2f} does not clear the {MIN_OOS_SHARPE:.2f} bar")
    if not oos["sharpe"] > buyhold_oos["sharpe"]:
        reasons.append(
            f"OOS Sharpe {oos['sharpe']:.2f} does not beat buy-and-hold OOS Sharpe {buyhold_oos['sharpe']:.2f}"
        )
    if not holdout["total_return"] > 0:
        reasons.append(f"Holdout total return {holdout['total_return']:.2%} is not positive")
    if sens["stability"] < MIN_STABILITY:
        reasons.append(
            f"Parameter stability {sens['stability']:.2f} is below the {MIN_STABILITY:.2f} bar "
            f"({sens['within_tolerance']} of {sens['grid_size']} combos within "
            f"{STABILITY_TOLERANCE} Sharpe of the best)"
        )
    if oos["trades"] < MIN_TRADES:
        reasons.append(f"Only {oos['trades']} out-of-sample trades; at least {MIN_TRADES} are required")
    return ("rejected" if reasons else "accepted"), reasons


def _sensitivity(combos: list[dict], frozen: dict) -> dict:
    sharpes = [c["metrics"]["sharpe"] for c in combos]
    best = max(sharpes)
    near = sum(s >= best - STABILITY_TOLERANCE for s in sharpes)
    chosen = next(c["metrics"]["sharpe"] for c in combos if c["params"] == frozen)
    return {
        "tolerance": STABILITY_TOLERANCE,
        "best_oos_sharpe": best,
        "grid_size": len(combos),
        "within_tolerance": near,
        "stability": near / len(combos),
        "frozen_params": frozen,
        "chosen_rank": 1 + sum(s > chosen for s in sharpes),
        "combos": combos,
    }


def _ledger(bt: Backtest, strategy: str, segment: str, window) -> list[dict]:
    keep = ("date", "symbol", "side", "qty", "ref_open", "fill_price", "fee", "slippage_cost")
    return [{"strategy": strategy, "segment": segment, "window": window, **{k: t[k] for k in keep}} for t in bt.trades]


def _events(bt: Backtest, strategy: str, segment: str, window) -> list[dict]:
    return [{"strategy": strategy, "segment": segment, "window": window, **e} for e in bt.missing_events]


def _headline(accepted: int, total: int) -> str:
    rejected = total - accepted
    if accepted == 0:
        lead = "The requested strategy was rejected" if total == 1 else f"All {total} strategies were rejected"
        return (
            f"{lead} on this synthetic dataset: no strategy cleared every out-of-sample, benchmark, "
            "holdout, stability and trade-count check."
        )
    return (
        f"{accepted} of {total} {'strategy' if total == 1 else 'strategies'} cleared every check and "
        f"{rejected} {'was' if rejected == 1 else 'were'} rejected; this is a result on synthetic data "
        "only, not evidence of an edge in real markets."
    )


def run_research(panel: Panel, request: dict) -> dict:
    if request.get("allow_short", False):
        raise ProtocolError(SHORT_ERROR)
    costs = Costs(float(request["costs"]["fee_bps"]), float(request["costs"]["slippage_bps"]))
    specs = [get_strategy(s) for s in request["strategies"]]
    n = panel.n_days
    h = holdout_start_index(n, request["holdout_fraction"])
    holdout_start = panel.dates[h]
    windows = make_windows(h, request["walk_forward"]["train_days"], request["walk_forward"]["test_days"])
    dev = panel.upto(h - 1)

    accounting = {"backtests_checked": 0, "max_abs_error": 0.0}

    def checked(bt: Backtest) -> Backtest:
        accounting["max_abs_error"] = max(accounting["max_abs_error"], reconcile(bt))
        accounting["backtests_checked"] += 1
        return bt

    oos_cache: dict[tuple, Backtest] = {}

    def oos_run(spec: Strategy, params: dict, w: Window) -> Backtest:
        key = (spec.id, params_key(params), w.index)
        if key not in oos_cache:
            oos_cache[key] = checked(run_strategy(dev, spec, params, w.test_start, w.test_end, costs))
        return oos_cache[key]

    experiments: list[dict] = []
    trades: list[dict] = []
    events: list[dict] = []
    walkforward: dict[str, list] = {}
    sensitivity: dict[str, dict] = {}
    oos_curves: dict[str, Curve] = {}
    frozen: dict[str, dict] = {}

    for spec in specs:
        rows, curves = [], []
        for w in windows:
            chosen, evaluated = select_params(spec, dev.upto(w.train_end), w, costs, holdout_start)
            for p, bt, m in evaluated:
                checked(bt)
                experiments.append(_experiment(spec.id, p, w.index, "in_sample", m))
            bt = oos_run(spec, chosen, w)
            c = curve(bt)
            m_oos = metrics(c)
            experiments.append(_experiment(spec.id, chosen, w.index, "out_of_sample", m_oos))
            trades += _ledger(bt, spec.id, "out_of_sample", w.index)
            events += _events(bt, spec.id, "out_of_sample", w.index)
            m_is = next(m for p, _, m in evaluated if p == chosen)
            rows.append({"window": w.index, "chosen_params": chosen, "in_sample": m_is, "out_of_sample": m_oos})
            curves.append(c)
        walkforward[spec.id] = rows
        oos_curves[spec.id] = stitch(curves)
        frozen[spec.id] = dict(rows[-1]["chosen_params"])

        combos = []
        for p in spec.params_grid:
            m = metrics(stitch([curve(oos_run(spec, p, w)) for w in windows]))
            experiments.append(_experiment(spec.id, p, "sensitivity", "out_of_sample", m))
            combos.append({"params": dict(p), "metrics": m})
        sensitivity[spec.id] = _sensitivity(combos, frozen[spec.id])

    # Every strategy's parameters are frozen above. Only now is the holdout touched, once each.
    holdout_calls: Counter = Counter()
    holdout_curves: dict[str, Curve] = {}
    holdout_evals = []
    for spec in specs:
        bt = checked(evaluate_holdout(spec, frozen[spec.id], panel, h, costs))
        holdout_calls[spec.id] += 1
        holdout_curves[spec.id] = curve(bt)
        m = metrics(holdout_curves[spec.id])
        experiments.append(_experiment(spec.id, frozen[spec.id], "holdout", "holdout", m))
        holdout_evals.append({"strategy": spec.id, "frozen_params": frozen[spec.id], "metrics": m})
        trades += _ledger(bt, spec.id, "holdout", "holdout")
        events += _events(bt, spec.id, "holdout", "holdout")

    oos_start, oos_end = windows[0].test_start, windows[-1].test_end
    bh_oos = curve(checked(buy_and_hold(dev, oos_start, oos_end, costs)))
    bh_hold = curve(checked(buy_and_hold(panel, h, n - 1, costs)))
    oos_span = [panel.day(oos_start), panel.day(oos_end)]
    hold_span = [panel.day(h), panel.day(n - 1)]
    benchmarks = {
        "buyhold": {
            "description": (
                "equal-weight (1/n) buy-and-hold of every symbol, bought at the first open of the span "
                "with the same fee and slippage, never rebalanced"
            ),
            "oos": {"span": oos_span, "metrics": metrics(bh_oos)},
            "holdout": {"span": hold_span, "metrics": metrics(bh_hold)},
        },
        "cash": {
            "description": "100,000 in cash earning 0 for the whole span",
            "oos": {"span": oos_span, "metrics": metrics(cash_curve(len(bh_oos.returns)))},
            "holdout": {"span": hold_span, "metrics": metrics(cash_curve(len(bh_hold.returns)))},
        },
    }

    results = []
    for spec in specs:
        oos_m = metrics(oos_curves[spec.id])
        hold_m = metrics(holdout_curves[spec.id])
        verdict, reasons = judge(oos_m, benchmarks["buyhold"]["oos"]["metrics"], hold_m, sensitivity[spec.id])
        results.append(
            {
                "id": spec.id,
                "name": spec.name,
                "verdict": verdict,
                "reasons": reasons,
                "oos_metrics": oos_m,
                "holdout_metrics": hold_m,
                "frozen_params": frozen[spec.id],
                "stability": sensitivity[spec.id]["stability"],
                "chosen_rank": sensitivity[spec.id]["chosen_rank"],
            }
        )
    accepted = sum(r["verdict"] == "accepted" for r in results)

    # Lookahead probe: signals on data truncated at a seeded cutoff must equal the full-data
    # signals on every date up to the cutoff.
    rng = np.random.Generator(np.random.PCG64([request["dataset"]["seed"], 1]))
    cutoff = int(rng.integers(WARMUP_PREFIX, n - 1))
    probe = []
    for spec in specs:
        full = spec.states(panel, frozen[spec.id])[: cutoff + 1]
        truncated = spec.states(panel.upto(cutoff), frozen[spec.id])
        probe.append({"strategy": spec.id, "params": frozen[spec.id], "equal": bool(np.array_equal(full, truncated))})

    equity = _equity_table(panel, specs, oos_start, oos_end, h, oos_curves, holdout_curves, bh_oos, bh_hold)
    return {
        "costs": {"fee_bps": costs.fee_bps, "slippage_bps": costs.slippage_bps},
        "holdout_start": panel.day(h),
        "windows": [
            {
                "index": w.index,
                "train_start": panel.day(w.train_start),
                "train_end": panel.day(w.train_end),
                "test_start": panel.day(w.test_start),
                "test_end": panel.day(w.test_end),
            }
            for w in windows
        ],
        "walkforward": walkforward,
        "experiments": experiments,
        "sensitivity": sensitivity,
        "holdout": {
            "span": hold_span,
            "sealed": True,
            "selection_frozen_before_holdout": True,
            "evaluations": holdout_evals,
        },
        "benchmarks": benchmarks,
        "results": results,
        "summary": {
            "accepted": accepted,
            "rejected": len(results) - accepted,
            "headline": _headline(accepted, len(results)),
        },
        "checks": {
            "accounting": {
                **accounting,
                "tolerance": ACCOUNTING_TOLERANCE,
                "passed": accounting["max_abs_error"] < ACCOUNTING_TOLERANCE,
            },
            "lookahead_probe": {
                "cutoff_date": panel.day(cutoff),
                "strategies": probe,
                "passed": all(p["equal"] for p in probe),
            },
            "determinism": {
                "note": (
                    "All randomness comes from numpy PCG64 seeded by the request seed. Outputs contain no "
                    "timestamps or paths; JSON is written with sorted keys and floats rounded to 10 "
                    "significant digits, CSV money columns use fixed decimals, and dataset.csv.gz is "
                    "written with gzip mtime=0. The same request gives byte-identical files."
                )
            },
            "holdout": {
                "evaluated_once": all(holdout_calls[s.id] == 1 for s in specs),
                "evaluations_per_strategy": dict(holdout_calls),
                "selection_frozen_before_holdout": True,
            },
            "missing_data_events": events,
        },
        "trades": trades,
        "equity": equity,
    }


def _experiment(strategy: str, params: dict, window, segment: str, m: dict) -> dict:
    return {"strategy": strategy, "params": dict(params), "window": window, "segment": segment, **m}


def _equity_table(panel, specs, oos_start, oos_end, h, oos_curves, holdout_curves, bh_oos, bh_hold) -> dict:
    """OOS curves continue into the holdout by chaining holdout returns onto the OOS end value."""

    def chained(oos: Curve, hold: Curve) -> np.ndarray:
        o = INITIAL_CASH * growth(oos)
        return np.concatenate((o, o[-1] * growth(hold)))

    columns = {s.id: chained(oos_curves[s.id], holdout_curves[s.id]) for s in specs}
    columns["buyhold"] = chained(bh_oos, bh_hold)
    oos_days = list(range(oos_start, oos_end + 1))
    hold_days = list(range(h, panel.n_days))
    columns["cash"] = np.full(len(oos_days) + len(hold_days), INITIAL_CASH)
    return {
        "dates": [panel.day(t) for t in oos_days + hold_days],
        "segments": ["out_of_sample"] * len(oos_days) + ["holdout"] * len(hold_days),
        "columns": columns,
    }


def assumptions(costs: dict) -> dict:
    def item(text: str, **fields) -> dict:
        return {**fields, "text": text}

    return {
        "signal_timing": item(SIGNAL_TIMING, rule="close_of_day_t"),
        "fill_timing": item(
            "Orders fill at the open of the next bar (t+1). A window's first open is driven by the "
            "state at the close of the bar before the window.",
            rule="next_open",
        ),
        "fees": item(
            f"Fee = {costs['fee_bps']} bps of absolute traded notional, paid in cash on every fill.",
            model="proportional",
            fee_bps=costs["fee_bps"],
        ),
        "slippage": item(
            f"Fixed adverse slippage of {costs['slippage_bps']} bps: buys fill at open * (1 + s), sells at "
            "open * (1 - s). It is embedded in fill prices and also reported separately as "
            "sum(|fill - open| * qty). No other market impact is modelled.",
            model="fixed_bps_adverse",
            slippage_bps=costs["slippage_bps"],
        ),
        "position_limits": item(
            f"Equal weight among symbols currently long, capped at {MAX_WEIGHT} per symbol, so gross "
            "exposure is at most 1.0. Targets are sized at the signal close: floor(weight * equity / close).",
            allocation="equal_weight_among_long",
            max_weight_per_symbol=MAX_WEIGHT,
            max_gross_exposure=1.0,
        ),
        "cash": item(
            f"Each backtest starts with {INITIAL_CASH:,.0f} in cash. Cash earns 0. No leverage: a buy that "
            "cash cannot cover (including its fee) is reduced to the whole shares cash covers.",
            initial=INITIAL_CASH,
            interest_rate=0.0,
            leverage=False,
        ),
        "shorting": item("Short selling is not supported; allow_short must be false.", supported=False),
        "missing_data": item(
            "A missing bar (NaN) cannot be traded: its order is deferred to the symbol's next valid open, "
            "the position is marked at the last valid close, and each such day is recorded in "
            "checks.json. Signals are computed on the symbol's valid bars only and the last state is "
            "carried across the gap.",
            rule="defer_and_mark_last_close",
        ),
        "warmup": item(
            f"The first {WARMUP_PREFIX} development bars (the largest warm-up in the registry) are never "
            "evaluated; they prime indicators. Each backtest computes signals from all bars before its "
            "start, never from bars after it. A strategy is flat until its own warm-up is complete.",
            prefix_bars=WARMUP_PREFIX,
        ),
        "calendar": item(
            "Synthetic Monday to Friday business days from 2015-01-02 with no exchange holidays.",
            kind="synthetic_business_days",
            holidays=False,
        ),
        "share_rounding": item("Whole shares only, rounded down.", rule="floor"),
        "rebalance": item(
            "Targets are recomputed only when the set of long symbols changes. Entries and exits always "
            "execute; a symbol that stays long is resized to the new equal weight only if its share count "
            f"is more than {REBALANCE_BAND:.0%} off target. No calendar rebalancing. Sells execute before "
            "buys at the same open.",
            rule="on_long_set_change",
            resize_band=REBALANCE_BAND,
        ),
        "holdout_split": item(
            "The last floor(days * holdout_fraction) dates are the sealed holdout, evaluated once per "
            "strategy with parameters frozen from the last walk-forward window.",
            rounding="floor",
        ),
        "window_boundaries": item(
            "Each walk-forward backtest starts flat with the initial cash. Positions open at a window's "
            "end are marked at that close and not charged an exit; the next window starts flat, so a "
            "position held across a boundary pays entry costs again. OOS segments are contiguous and "
            "chained by returns.",
        ),
        "equity_chaining": item(
            "equity.csv shows the chained OOS curve and then continues into the holdout by chaining "
            "holdout returns onto the last OOS value. Dates between the last OOS window and the holdout "
            "start (if any) are not part of either curve.",
        ),
        "metrics": item(
            f"Daily simple returns; {TRADING_DAYS} trading days per year; Sharpe = mean / std (ddof=1) * "
            f"sqrt({TRADING_DAYS}) with rf = 0 and 0.0 for a flat curve; max_drawdown is a negative "
            "fraction; turnover = sum of daily traded notional / previous close equity; exposure = mean "
            "gross weight at the close; stitched fees and slippage are summed over segments, each run on "
            "the initial cash.",
            trading_days_per_year=TRADING_DAYS,
        ),
    }
