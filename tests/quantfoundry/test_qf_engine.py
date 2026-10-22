"""Simulator mechanics, missing-data rule, metrics, verdicts and protocol helpers."""

import math

import numpy as np
import pytest
from qf_helpers import SMALL_REQUEST, make_panel, request

from quantfoundry.research.metrics import Curve, metrics
from quantfoundry.research.protocol import (
    MAX_WINDOWS,
    WARMUP_PREFIX,
    ProtocolError,
    fmt_sharpe,
    fmt_t_stat,
    holdout_start_index,
    judge,
    make_windows,
    run_research,
)
from quantfoundry.sim.engine import Costs, backtest, reconcile
from quantfoundry.strategies import REGISTRY


def _states(days, n, on: dict[int, int]) -> np.ndarray:
    """Symbol j is long from the close of day on[j] onward."""
    s = np.zeros((days, n), dtype=bool)
    for j, day in on.items():
        s[day:, j] = True
    return s


def test_fill_fee_and_slippage_arithmetic():
    panel = make_panel([100.0, 102.0, 103.0], open_=[100.0, 101.0, 102.5])
    bt = backtest(panel, _states(3, 1, {0: 0}), 1, 2, Costs(fee_bps=10, slippage_bps=20))
    (tr,) = bt.trades
    assert tr["date"] == panel.day(1) and tr["side"] == "buy"
    assert tr["qty"] == 250  # floor(0.25 * 100,000 / close 100)
    assert tr["fill_price"] == pytest.approx(101.0 * 1.002)
    assert tr["fee"] == pytest.approx(250 * 101.202 * 0.001)
    assert tr["slippage_cost"] == pytest.approx(250 * 0.202)
    assert bt.cash[0] == pytest.approx(100_000 - 250 * 101.202 * 1.001)
    assert bt.equity[1] == pytest.approx(bt.cash[1] + 250 * 103.0)


def test_buy_is_reduced_when_cash_is_short():
    panel = make_panel([100.0, 100.0, 100.0])
    bt = backtest(panel, _states(3, 1, {0: 0}), 1, 2, Costs(fee_bps=50, slippage_bps=100), max_weight=1.0)
    (tr,) = bt.trades
    assert tr["qty"] == math.floor(100_000 / (101.0 * 1.005))
    assert bt.cash.min() >= 0
    assert reconcile(bt) < 1e-9


def test_missing_bar_defers_order_and_marks_last_close():
    close = np.array([[10.0, 20.0], [10.0, 20.0], [11.0, np.nan], [12.0, 22.0], [13.0, np.nan], [14.0, 24.0]])
    panel = make_panel(close)
    bt = backtest(panel, _states(6, 2, {0: 1, 1: 1}), 2, 5, Costs())
    by_symbol = {}
    for tr in bt.trades:
        by_symbol.setdefault(tr["symbol"], []).append(tr)
    assert [t["date"] for t in by_symbol["T00"]] == [panel.day(2)]
    assert [t["date"] for t in by_symbol["T01"]] == [panel.day(3)], "deferred to the next valid open"
    assert by_symbol["T01"][0]["qty"] == 1250  # sized at the signal close: 0.25 * 100,000 / 20
    assert bt.missing_events == [
        {"date": panel.day(2), "symbol": "T01", "held_qty": 0, "order_deferred": True},
        {"date": panel.day(4), "symbol": "T01", "held_qty": 1250, "order_deferred": False},
    ]
    # Day 4: T01 has no bar and is marked at its last valid close (22).
    qa = by_symbol["T00"][0]["qty"]
    assert bt.equity[2] == pytest.approx(bt.cash[2] + qa * 13.0 + 1250 * 22.0)
    assert reconcile(bt) < 1e-9


def test_rebalances_only_when_the_long_set_changes():
    panel = make_panel(np.full((12, 5), 50.0))
    # Four symbols long from day 0 (weight 0.25 each); the fifth joins at day 5 (weight 0.20).
    bt = backtest(panel, _states(12, 5, {0: 0, 1: 0, 2: 0, 3: 0, 4: 5}), 1, 11, Costs(1, 5))
    days = sorted({t["date"] for t in bt.trades})
    assert days == [panel.day(1), panel.day(6)]
    day6 = [t for t in bt.trades if t["date"] == panel.day(6)]
    assert [t["side"] for t in day6] == ["sell"] * 4 + ["buy"], "sells execute before buys"
    assert bt.market_value[-1] / bt.equity[-1] <= 1.0


def test_position_above_cap_is_trimmed_at_the_next_decision():
    close = np.full((10, 4), 50.0)
    close[3:, 0] = 60.0  # T00 drifts to 30,000 / 105,000 = 0.286 of equity
    panel = make_panel(close)
    states = _states(10, 4, {0: 0, 1: 0, 2: 0, 3: 0})
    states[5:, 3] = False  # T03 exits at the close of day 5: a decision, weight stays 0.25
    bt = backtest(panel, states, 1, 9, Costs())
    day6 = {t["symbol"]: t for t in bt.trades if t["date"] == panel.day(6)}
    assert sorted(day6) == ["T00", "T03"], "T01 and T02 sit inside the band and are left alone"
    assert day6["T03"]["qty"] == 500 and day6["T00"]["side"] == "sell"
    assert 500 - day6["T00"]["qty"] == int(0.25 * 105_000 // 60)  # trimmed to the cap


def test_liquidation_sells_everything_at_the_final_close():
    close = np.array([[10.0, 20.0], [10.0, 20.0], [11.0, 21.0], [12.0, np.nan]])
    panel = make_panel(close)
    costs = Costs(fee_bps=10, slippage_bps=20)
    bt = backtest(panel, _states(4, 2, {0: 0, 1: 0}), 1, 3, costs, liquidate=True)
    last = [t for t in bt.trades if t["day"] == 3]
    assert [(t["symbol"], t["side"]) for t in last] == [("T00", "sell"), ("T01", "sell")]
    assert last[0]["ref_open"] == 12.0 and last[1]["ref_open"] == 21.0, "missing final bar: last valid close"
    assert last[0]["fill_price"] == pytest.approx(12.0 * 0.998)
    assert bt.market_value[-1] == 0.0 and bt.equity[-1] == bt.cash[-1]
    assert reconcile(bt) < 1e-9
    kept = backtest(panel, _states(4, 2, {0: 0, 1: 0}), 1, 3, costs)
    assert bt.equity[-1] < kept.equity[-1], "the exit costs are charged"


def test_signals_skip_missing_bars_and_carry_state():
    close = 50.0 + 0.25 * np.arange(400)
    close[300] = np.nan
    panel = make_panel(close)
    states = REGISTRY["trend"].states(panel, {"fast": 10, "slow": 200})[:, 0]
    assert not states[:199].any()
    assert states[199:].all(), "one missing bar must not reset a 200-bar SMA"


def test_metrics_on_known_series():
    r = np.array([0.01, -0.02, 0.03])
    m = metrics(Curve(r, np.array([1.0, 0.5, 0.0]), np.array([1.0, 0.0, 0.5]), 3, 1, 1.5, 2.5))
    assert m["total_return"] == pytest.approx(1.01 * 0.98 * 1.03 - 1)
    assert m["max_drawdown"] == pytest.approx(0.98 - 1)
    assert m["sharpe"] == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))
    assert m["volatility"] == pytest.approx(r.std(ddof=1) * math.sqrt(252))
    assert m["cagr"] == pytest.approx((1.01 * 0.98 * 1.03) ** (252 / 3) - 1)
    assert (m["trades"], m["round_trips"], m["fees_paid"], m["slippage_paid"], m["days"]) == (3, 1, 1.5, 2.5, 3)
    assert m["exposure"] == pytest.approx(0.5) and m["turnover"] == pytest.approx(1.5)
    flat = metrics(Curve(np.zeros(10), np.zeros(10), np.zeros(10), 0, 0, 0.0, 0.0))
    assert flat["sharpe"] == 0.0 and flat["total_return"] == 0.0 and flat["max_drawdown"] == 0.0


def test_judge_lists_every_failing_reason():
    bad = {"sharpe": 0.12, "trades": 14, "round_trips": 2, "days": 189}
    weak = {"stability": 1 / 9, "within_tolerance": 1, "grid_size": 9}
    verdict, reasons = judge(bad, {"sharpe": 0.5}, {"total_return": -0.02}, weak)
    assert verdict == "rejected"
    assert reasons == [
        "OOS Sharpe 0.120 does not clear the 0.30 bar",
        "OOS Sharpe t-statistic 0.104 is below the 2.0 significance bar (189 out-of-sample days)",
        "OOS Sharpe 0.120 does not beat buy-and-hold OOS Sharpe 0.500",
        "Holdout total return -2.00% (liquidated at the final close) is not positive",
        "Parameter stability 0.11 is below the 0.30 bar (1 of 9 combos within 0.5 Sharpe of the best)",
        "Only 2 completed round trips; at least 10 are required",
    ]
    stable = {"stability": 0.5, "within_tolerance": 5, "grid_size": 9}
    # A Sharpe of 0.9 clears the 0.30 bar but over 189 days its t-statistic is only 0.78.
    short = {"sharpe": 0.9, "trades": 80, "round_trips": 40, "days": 189}
    assert judge(short, {"sharpe": 0.5}, {"total_return": 0.03}, stable) == (
        "rejected",
        ["OOS Sharpe t-statistic 0.779 is below the 2.0 significance bar (189 out-of-sample days)"],
    )
    long = {"sharpe": 0.9, "trades": 80, "round_trips": 40, "days": 1260}  # t = 0.9 * sqrt(5) = 2.01
    assert judge(long, {"sharpe": 0.5}, {"total_return": 0.03}, stable) == ("accepted", [])


def test_boundary_values_print_on_the_correct_side():
    assert fmt_sharpe(0.2996) == "0.300" and fmt_sharpe(0.3004) == "0.3004"
    assert fmt_t_stat(1.9996) == "1.9996" and fmt_t_stat(2.0004) == "2.000"
    assert fmt_sharpe(-1.23456) == "-1.235"


def test_windows_and_holdout_split():
    assert holdout_start_index(1512, 0.2) == 1512 - 302  # floor
    assert holdout_start_index(800, 0.29) == 800 - 232  # exact decimal floor, not float
    windows = make_windows(1210, 504, 126)
    assert len(windows) == 4 and windows[-1].test_end == 1209, "last test window ends the day before the holdout"
    assert windows[0].train_start == 202 >= WARMUP_PREFIX
    for a, b in zip(windows, windows[1:], strict=False):
        assert b.test_start == a.test_end + 1 and b.train_start == a.train_start + 126
    eight = make_windows(10_000, 252, 63)
    assert len(eight) == MAX_WINDOWS and eight[-1].test_end == 9_999 and [w.index for w in eight] == list(range(8))
    with pytest.raises(ProtocolError, match="needs 1015"):
        make_windows(1000, 756, 59)


def test_short_selling_is_rejected(small_panel):
    with pytest.raises(ProtocolError, match="long-only"):
        run_research(small_panel, request(allow_short=True))


def test_registry_is_bounded():
    assert sorted(REGISTRY) == ["breakout", "meanrev", "trend"]
    for spec in REGISTRY.values():
        assert 1 <= len(spec.params_grid) <= 9
        assert spec.snapshot()["signal_timing"].startswith("computed from bars up to and including")
    assert {REGISTRY["trend"].warmup_bars(p) for p in REGISTRY["trend"].params_grid} == {50, 100, 200}
    assert REGISTRY["breakout"].warmup_bars({"N": 55, "k": 0.5}) == 56
    assert REGISTRY["meanrev"].warmup_bars({"lookback": 40, "entry_z": 1.0}) == 40
    assert all(p["fast"] < p["slow"] for p in REGISTRY["trend"].params_grid)
    assert SMALL_REQUEST["allow_short"] is False
