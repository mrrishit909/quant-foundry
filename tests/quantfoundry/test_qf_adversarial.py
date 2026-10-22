"""Adversarial review of the research protocol: one test per probe.

Tests marked `finding(...)` document a real defect: xfail(strict=True, raises=AssertionError), so
the suite stays green while the defect exists and turns red once it is fixed (remove the marker
then). Their preconditions use `require` (pytest.fail), so a broken setup fails loudly instead of
passing as an expected failure. Unmarked tests confirm that a property holds.

All findings of the first review are fixed; their tests now assert the fixed property. Where a
test's precondition only held while the defect existed (e.g. "this scenario is accepted"), it was
rewritten to check the rule itself.
"""

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from qf_helpers import SMALL_REQUEST, make_panel, request, synthetic_panel

from quantfoundry.data import synthetic
from quantfoundry.data.ingest import PRICE_COLUMNS
from quantfoundry.data.panel import Panel
from quantfoundry.research import protocol
from quantfoundry.sim import engine
from quantfoundry.sim.engine import Costs
from quantfoundry.strategies import REGISTRY

ROOT = Path(__file__).resolve().parents[2]
SMALL_COSTS = Costs(SMALL_REQUEST["costs"]["fee_bps"], SMALL_REQUEST["costs"]["slippage_bps"])


def finding(reason: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"FINDING: {reason}")


def require(cond, msg: str) -> None:
    if not cond:
        pytest.fail(f"precondition broken: {msg}")


def noise_panel(seed: int, days: int = 756, n: int = 3) -> Panel:
    """Zero-drift geometric random walk: no strategy has an edge by construction."""
    rng = np.random.default_rng(seed)
    close = 50.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, (days, n)), axis=0))
    prev = np.vstack([np.full(n, 50.0), close[:-1]])
    open_ = prev * np.exp(rng.normal(0.0, 0.003, (days, n)))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0.0, 0.005, (days, n))))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0.0, 0.005, (days, n))))
    return make_panel(close, open_, high, low)


def completed_round_trips(trades: list[dict], segment: str = "out_of_sample") -> dict[str, int]:
    """Sells that take a position back to zero, per strategy (a fill is not a round trip)."""
    held: dict[tuple, int] = {}
    exits: dict[str, int] = {}
    for t in trades:
        if t["segment"] != segment:
            continue
        key = (t["strategy"], t["window"], t["symbol"])
        held[key] = held.get(key, 0) + (t["qty"] if t["side"] == "buy" else -t["qty"])
        if t["side"] == "sell" and held[key] == 0:
            exits[t["strategy"]] = exits.get(t["strategy"], 0) + 1
    return exits


def liquidated_return(bt, costs: Costs) -> float:
    """Total return if the positions open at the last close were sold there with the run's costs."""
    f, s = costs.fee_bps / 1e4, costs.slippage_bps / 1e4
    index = {sym: j for j, sym in enumerate(bt.symbols)}
    qty = np.zeros(len(bt.symbols))
    for t in bt.trades:
        qty[index[t["symbol"]]] += t["qty"] if t["side"] == "buy" else -t["qty"]
    exit_cost = float(qty @ bt.marks[-1]) * (1.0 - (1.0 - s) * (1.0 - f))
    return (bt.equity[-1] - exit_cost) / bt.initial_cash - 1.0


def load_hooks():
    spec = importlib.util.spec_from_file_location("project_hooks", ROOT / "project_hooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def small_research(small_panel):
    return protocol.run_research(small_panel, SMALL_REQUEST)


# ---------------------------------------------------------------------------------------------
# Findings of the first review (fixed; each test now asserts the fixed property)
# ---------------------------------------------------------------------------------------------


def test_trade_minimum_counts_round_trips(small_research):
    """The minimum is judged on completed round trips, not fills (window-start buys do not count)."""
    trips = completed_round_trips(small_research["trades"])
    require(sum(trips.values()) > 0, "some strategy completes round trips OOS")
    for r in small_research["results"]:
        n = trips.get(r["id"], 0)
        assert r["oos_metrics"]["round_trips"] == n, r["id"]
        assert r["oos_metrics"]["trades"] >= 2 * n, "every round trip is at least one buy and one sell"
        failed_rule = any("round trips" in x for x in r["reasons"])
        assert failed_rule == (n < protocol.MIN_ROUND_TRIPS), (r["id"], n, r["reasons"])


def test_accepted_strategy_has_real_round_trips():
    """Buy-and-hold-like trend (no exits, only window-start buys) must not pass the trade minimum."""
    rng = np.random.default_rng(0)
    days, drift = 1000, np.array([0.0015, 0.0015, -0.0015, -0.0015])
    close = 50.0 * np.exp(np.cumsum(drift + rng.normal(0.0, 0.004, (days, 4)), axis=0))
    panel = make_panel(close, open_=np.vstack([np.full(4, 50.0), close[:-1]]))
    res = protocol.run_research(
        panel, request(**{"strategies": ["trend"], "costs.fee_bps": 1.0, "costs.slippage_bps": 5.0})
    )
    (r,) = res["results"]
    oos = [t for t in res["trades"] if t["segment"] == "out_of_sample"]
    trips = completed_round_trips(res["trades"]).get("trend", 0)
    require(sum(t["side"] == "buy" for t in oos) >= len(res["windows"]), "trend re-buys at every window start")
    require(trips < protocol.MIN_ROUND_TRIPS, f"the scenario has few real round trips ({trips})")
    assert r["oos_metrics"]["round_trips"] == trips
    assert r["verdict"] == "rejected"
    assert f"Only {trips} completed round trips; at least {protocol.MIN_ROUND_TRIPS} are required" in r["reasons"]


def test_pure_noise_is_never_accepted():
    accepted = []
    for seed in (3, 5, 23):
        res = protocol.run_research(noise_panel(seed), request(**{"dataset.seed": seed}))
        n_oos = res["equity"]["segments"].count("out_of_sample")
        for r in res["results"]:
            if r["verdict"] == "accepted":
                sr = r["oos_metrics"]["sharpe"]
                accepted.append(
                    f"seed {seed} {r['id']}: OOS Sharpe {sr:.3f} over {n_oos} days, t = {sr * math.sqrt(n_oos / 252):.2f}"
                )
    assert accepted == [], "; ".join(accepted)


def test_holdout_gate_survives_liquidation():
    """The holdout run ends flat: its reported return already includes selling at the final close."""
    seed = 9
    panel = noise_panel(seed)
    res = protocol.run_research(panel, request(**{"dataset.seed": seed}))
    h = protocol.holdout_start_index(panel.n_days, SMALL_REQUEST["holdout_fraction"])
    for r in res["results"]:
        bt = protocol.evaluate_holdout(REGISTRY[r["id"]], r["frozen_params"], panel, h, SMALL_COSTS)
        reported = r["holdout_metrics"]["total_return"]
        require(bt.trades, f"{r['id']} trades in the holdout")
        assert abs(bt.equity[-1] / bt.initial_cash - 1.0 - reported) < 1e-12, "re-run matches the report"
        assert bt.market_value[-1] == 0.0 and bt.equity[-1] == bt.cash[-1], "nothing left open"
        assert liquidated_return(bt, SMALL_COSTS) == pytest.approx(reported, abs=1e-12)
        final_sells = [t for t in bt.trades if t["day"] == panel.n_days - 1 and t["side"] == "sell"]
        for t in final_sells:
            assert t["fill_price"] == pytest.approx(t["ref_open"] * (1 - SMALL_COSTS.slippage_bps / 1e4))
        failed_rule = any(x.startswith("Holdout") for x in r["reasons"])
        assert failed_rule == (not reported > 0), (r["id"], reported, r["reasons"])


def test_generator_scale_ignores_holdout(monkeypatch):
    """The price rescale only reads bars that are development data for EVERY allowed holdout_fraction."""
    seed, symbols, days = 123, 3, 756
    never_holdout = days - (3 * days) // 10  # bars before the earliest possible holdout (fraction 0.3)
    assert all(
        n - (3 * n) // 10 <= protocol.holdout_start_index(n, f100 / 100)
        for n in range(756, 2521)
        for f100 in range(10, 31)
    )
    real, _ = synthetic.generate(seed, symbols, days, "balanced")
    monkeypatch.setattr(synthetic, "MIN_LOW", 0.0)  # scale = max(1, 0 / min low) = 1: the unscaled series
    raw, _ = synthetic.generate(seed, symbols, days, "balanced")
    monkeypatch.undo()
    early = raw["date"] < np.sort(raw["date"].unique())[never_holdout]
    old_rule_leaks = []
    for sym in sorted(raw["symbol"].unique()):
        m = raw["symbol"] == sym
        s_full = max(1.0, synthetic.MIN_LOW / np.nanmin(raw.loc[m, "low"]))
        s_safe = max(1.0, synthetic.MIN_LOW / np.nanmin(raw.loc[m & early, "low"]))
        assert np.allclose(real.loc[m, PRICE_COLUMNS], raw.loc[m, PRICE_COLUMNS] * s_safe, equal_nan=True), sym
        if s_full != s_safe:
            old_rule_leaks.append(sym)
    require(old_rule_leaks, "this seed has a symbol whose all-time low lies in the holdout region")


def test_holdout_split_uses_exact_floor():
    bad = [
        (n, f100 / 100)
        for n in range(756, 2521)
        for f100 in range(10, 31)
        if protocol.holdout_start_index(n, f100 / 100) != n - (n * f100) // 100
    ]
    assert bad == [], f"holdout one day short for (days, fraction) in {bad}"


def test_walkforward_reaches_the_holdout():
    days, fraction, train, test = 2520, 0.1, 252, 63  # a schema-valid request
    h = protocol.holdout_start_index(days, fraction)
    last = protocol.make_windows(h, train, test)[-1]
    unused = h - 1 - last.test_end
    assert unused < test, (
        f"{unused} of {h} development bars ({unused / h:.0%}) after the last OOS window are never evaluated; the "
        f"frozen params were trained on bars ending {h - 1 - last.train_end} bars before the holdout"
    )


def test_position_cap_holds_at_decision_time(monkeypatch):
    real = engine._orders
    worst = [0.0]

    def spy(long_set, equity, marks, max_weight, qty):
        orders = real(long_set, equity, marks, max_weight, qty)
        if max_weight == protocol.MAX_WEIGHT:
            for j in range(len(qty)):
                worst[0] = max(worst[0], orders.get(j, int(qty[j])) * marks[j] / equity)
        return orders

    monkeypatch.setattr(engine, "_orders", spy)
    protocol.run_research(synthetic_panel(seed=0), request(**{"dataset.seed": 0}))
    require(worst[0] > 0.2, "the spy saw strategy sizing decisions")
    assert worst[0] <= protocol.MAX_WEIGHT + 1e-12, f"post-decision weight {worst[0]:.4f} > {protocol.MAX_WEIGHT}"


def test_displayed_sharpe_separates_verdicts():
    sens = {"stability": 1.0, "within_tolerance": 9, "grid_size": 9}
    shown = {}
    for sharpe in (0.3004, 0.2996):
        # 20,000 OOS days keeps the t-statistic rule out of the way so only the 0.30 bar decides.
        oos = {"sharpe": sharpe, "trades": 50, "round_trips": 50, "days": 20_000}
        verdict, reasons = protocol.judge(oos, {"sharpe": 0.0}, {"total_return": 0.1}, sens)
        shown[verdict] = protocol.fmt_sharpe(sharpe)  # the format of report.md's table and reason strings
        if verdict == "rejected":
            assert reasons == [f"OOS Sharpe {shown[verdict]} does not clear the 0.30 bar"]
    require(set(shown) == {"accepted", "rejected"}, f"one of each verdict: {shown}")
    assert shown["accepted"] != shown["rejected"], f"report shows {shown} against the rule 'OOS Sharpe > 0.30'"
    assert float(shown["accepted"]) > 0.30 >= float(shown["rejected"])


def test_holdout_audit_flags_reused_holdout_data(tmp_path):
    hooks = load_hooks()
    state = tmp_path / "state"
    state.mkdir()

    def publish(run_id: str, span: list[str], fraction: float) -> dict:
        out = tmp_path / run_id
        out.mkdir()
        manifest = {"params": {"holdout_fraction": fraction}, "dataset": {"sha256": "same-dataset"}}
        holdout = {"span": span, "evaluations": [{"strategy": "trend", "frozen_params": {"fast": 10, "slow": 50}}]}
        (out / "manifest.json").write_text(json.dumps(manifest))
        (out / "holdout.json").write_text(json.dumps(holdout))
        hooks.on_publish(state, {"run_id": run_id}, out)
        return json.loads((state / "runs" / run_id / "holdout_audit.json").read_text())

    publish("run-a", ["2019-11-01", "2021-12-31"], 0.3)  # run A already saw the last 30%
    (b,) = publish("run-b", ["2021-06-01", "2021-12-31"], 0.1)["strategies"]  # B trains on part of A's holdout
    require(b["prior_evaluations"] == 1, "the ledger saw run A")
    assert b["contaminated"], f"run B audit: {b}"


def test_memory_lesson_groups_trade_count_reasons(tmp_path):
    hooks = load_hooks()
    firsts = [
        "Only 3 out-of-sample trades; at least 10 are required",
        "Only 5 out-of-sample trades; at least 10 are required",
        "Only 8 out-of-sample trades; at least 10 are required",
        "Holdout total return -1.00% is not positive",
        "Holdout total return -2.00% is not positive",
    ]
    runs = []
    for i, reason in enumerate(firsts):
        run_dir = tmp_path / "runs" / f"run-{i}"
        run_dir.mkdir(parents=True)
        strat = {"id": "trend", "verdict": "rejected", "reasons": [reason], "oos_metrics": {"sharpe": 0.1}}
        (run_dir / "results.json").write_text(json.dumps({"strategies": [strat]}))
        runs.append({"run_id": f"run-{i}", "status": "completed"})
    (tmp_path / "index.json").write_text(json.dumps({"runs": runs}))
    (lesson,) = [c for c in hooks.memory_candidates(tmp_path) if c["topic"].startswith("Strategy 'trend'")]
    require("Rejected in 5 of 5" in lesson["finding"], lesson["finding"])
    assert "'Holdout total'" not in lesson["finding"], (
        f"3 of 5 runs failed on trade count, lesson says: {lesson['finding']}"
    )


# ---------------------------------------------------------------------------------------------
# Properties that hold
# ---------------------------------------------------------------------------------------------


def test_sizing_never_reads_the_fill_day_bar(small_panel):
    """Orders sized at close t are unchanged when the whole bar t+1 (incl. its open) is perturbed.

    max_weight=0.1 keeps cash from binding, so the only legitimate use of the fill-day open (the
    cash-cover reduction) cannot trigger."""
    end = small_panel.n_days - 1
    for spec in REGISTRY.values():
        p = spec.params_grid[4]
        states = spec.states(small_panel, p)
        base = engine.backtest(small_panel, states, 200, end, SMALL_COSTS, max_weight=0.1)
        days = sorted({t["day"] for t in base.trades})[:8]
        require(days, f"{spec.id} trades")
        for k in days:
            bumped = [a.copy() for a in (small_panel.open, small_panel.high, small_panel.low, small_panel.close)]
            for a in bumped:
                a[k] *= 1.05
            panel = Panel(small_panel.dates, small_panel.symbols, *bumped, small_panel.volume)
            bt = engine.backtest(panel, spec.states(panel, p), 200, end, SMALL_COSTS, max_weight=0.1)
            want = [(t["day"], t["symbol"], t["side"], t["qty"]) for t in base.trades if t["day"] <= k]
            got = [(t["day"], t["symbol"], t["side"], t["qty"]) for t in bt.trades if t["day"] <= k]
            assert got == want, (spec.id, k)
            fills = [
                t["fill_price"] / u["fill_price"] for t, u in zip(bt.trades, base.trades, strict=False) if t["day"] == k
            ]
            assert fills and all(x == pytest.approx(1.05) for x in fills), (spec.id, k)


def test_both_sides_pay_adverse_slippage_and_fees(small_research):
    s, f = SMALL_COSTS.slippage_bps / 1e4, SMALL_COSTS.fee_bps / 1e4
    for t in small_research["trades"]:
        sign = 1.0 if t["side"] == "buy" else -1.0
        assert t["fill_price"] == pytest.approx(t["ref_open"] * (1.0 + sign * s), rel=1e-12)
        assert t["fee"] == pytest.approx(t["qty"] * t["fill_price"] * f, rel=1e-12)
        assert t["slippage_cost"] == pytest.approx(t["qty"] * t["ref_open"] * s, rel=1e-9)
        assert isinstance(t["qty"], int) and t["qty"] > 0
    assert {t["side"] for t in small_research["trades"]} == {"buy", "sell"}


def test_holdout_boundary_and_accounting_of_every_backtest(monkeypatch):
    """782 days at fraction 0.1: the last OOS window ends exactly on day h-1, the tightest boundary."""
    panel = synthetic_panel(days=782)
    req = request(**{"dataset.days": 782})
    n = panel.n_days
    h = protocol.holdout_start_index(n, req["holdout_fraction"])
    calls = []
    real = protocol.backtest

    def spy(view, states, start, end, costs, **kw):
        bt = real(view, states, start, end, costs, **kw)
        calls.append((view.n_days, start, end, bt))
        return bt

    monkeypatch.setattr(protocol, "backtest", spy)
    res = protocol.run_research(panel, req)
    monkeypatch.undo()
    require(protocol.make_windows(h, 252, 63)[-1].test_end == h - 1, "last window ends on h-1")

    holdout = [c for c in calls if c[1] >= h]
    dev = [c for c in calls if c[1] < h]
    assert len(holdout) == len(req["strategies"]) + 1  # each strategy once, plus buy-and-hold
    assert all(start == h and end == n - 1 and rows == n for rows, start, end, _ in holdout)
    assert all(rows <= h and end <= h - 1 for rows, _, end, _ in dev)
    assert any(end == h - 1 for _, _, end, _ in dev)
    assert all(panel.day(h) not in bt.dates for *_, bt in dev)
    for *_, bt in calls:
        assert (bt.cash >= -1e-9).all()
        assert (bt.market_value <= bt.equity * (1 + 1e-12)).all()  # gross exposure <= 1, no leverage
        held: dict[str, int] = {}
        for t in bt.trades:
            held[t["symbol"]] = held.get(t["symbol"], 0) + (t["qty"] if t["side"] == "buy" else -t["qty"])
            assert held[t["symbol"]] >= 0
    eq = res["equity"]
    i = eq["segments"].index("holdout")
    assert eq["dates"][i - 1] == panel.day(h - 1) and eq["dates"][i] == panel.day(h)
    assert len(set(eq["dates"])) == len(eq["dates"])


def test_stitched_oos_chains_window_segments(small_research):
    eq = small_research["equity"]
    oos_rows = [i for i, s in enumerate(eq["segments"]) if s == "out_of_sample"]
    windows = small_research["windows"]
    assert eq["dates"][oos_rows[0]] == windows[0]["test_start"] and eq["dates"][oos_rows[-1]] == windows[-1]["test_end"]
    for r in small_research["results"]:
        rows = small_research["walkforward"][r["id"]]
        chained = math.prod(1.0 + w["out_of_sample"]["total_return"] for w in rows) - 1.0
        assert r["oos_metrics"]["total_return"] == pytest.approx(chained, rel=1e-12, abs=1e-15)
        assert r["oos_metrics"]["trades"] == sum(w["out_of_sample"]["trades"] for w in rows)
        assert r["oos_metrics"]["fees_paid"] == pytest.approx(sum(w["out_of_sample"]["fees_paid"] for w in rows))
        assert eq["columns"][r["id"]][oos_rows[-1]] == pytest.approx(100_000 * (1.0 + chained))
        assert r["oos_metrics"]["max_drawdown"] <= 0.0 and r["holdout_metrics"]["max_drawdown"] <= 0.0
    bh = small_research["benchmarks"]["buyhold"]["oos"]
    assert bh["span"] == [windows[0]["test_start"], windows[-1]["test_end"]]


def test_flat_grid_is_stable_but_still_rejected():
    combos = [{"params": {"a": i}, "metrics": {"sharpe": 0.0}} for i in range(9)]
    sens = protocol._sensitivity(combos, {"a": 0})
    assert sens["stability"] == 1.0  # stability is relative to the best combo, so "all flat" scores 1.0
    oos = {"sharpe": 0.0, "trades": 0, "round_trips": 0, "days": 189}
    verdict, reasons = protocol.judge(oos, {"sharpe": 0.1}, {"total_return": 0.0}, sens)
    assert verdict == "rejected" and len(reasons) == 5  # bar, t-statistic, buy-and-hold, holdout, round trips


def test_headline_survives_publish_truncation():
    for total in (1, 2, 3):
        for accepted in range(total + 1):
            text = protocol._headline(accepted, total)
            assert len(text) <= 200 and "synthetic" in text  # project_hooks.headline keeps the first 200 chars
