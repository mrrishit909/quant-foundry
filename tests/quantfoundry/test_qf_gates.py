"""The eight hard release gates (run with `pytest -m gate`)."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest
from qf_helpers import (
    SMALL_REQUEST,
    file_hashes,
    load,
    make_panel,
    random_panel,
    read_csv,
    request,
    run_cli,
)

from quantfoundry.data.panel import Panel
from quantfoundry.outputs import REQUIRED_FILES, compact
from quantfoundry.research import protocol
from quantfoundry.research.metrics import curve, metrics
from quantfoundry.research.protocol import (
    HoldoutLeakError,
    Window,
    holdout_start_index,
    run_strategy,
)
from quantfoundry.sim.engine import Costs, backtest, reconcile
from quantfoundry.strategies import REGISTRY, Strategy


def _scale_rows(panel: Panel, rows: np.ndarray, factor: float) -> Panel:
    """Copy of `panel` with OHLC on the selected rows multiplied by `factor` (garbage prices)."""
    mask = rows[:, None]
    scaled = [np.where(mask, a * factor, a) for a in (panel.open, panel.high, panel.low, panel.close)]
    return Panel(panel.dates, panel.symbols, *scaled, panel.volume)


@pytest.mark.gate
def test_accounting_reconciles(small_panel):
    total_trades = 0
    for seed in range(60):
        rng = np.random.default_rng(seed)
        days, n = int(rng.integers(30, 160)), int(rng.integers(1, 7))
        panel = random_panel(rng, days, n, missing=int(rng.integers(0, 6)))
        flips = rng.random((days, n)) < rng.uniform(0.02, 0.3)
        states = (np.cumsum(flips, axis=0) % 2).astype(bool)
        costs = Costs(float(rng.uniform(0, 50)), float(rng.uniform(0, 100)))
        start = int(rng.integers(0, days // 3))
        end = int(rng.integers(start, days))
        bt = backtest(
            panel,
            states,
            start,
            end,
            costs,
            max_weight=float(rng.choice([0.25, 0.5, 1.0])),
            initial_cash=float(rng.uniform(1e3, 1e6)),
        )
        assert reconcile(bt) < 1e-6, f"seed {seed}"
        assert (bt.cash >= -1e-9).all(), "no leverage: cash never negative"
        held = {}
        for tr in bt.trades:
            held[tr["symbol"]] = held.get(tr["symbol"], 0) + (tr["qty"] if tr["side"] == "buy" else -tr["qty"])
            assert held[tr["symbol"]] >= 0, "long-only: a position never goes short"
        total_trades += len(bt.trades)
    assert total_trades > 500  # the loop really exercised the ledger

    for spec in REGISTRY.values():
        for p in spec.params_grid[::4]:
            bt = run_strategy(small_panel, spec, p, 200, small_panel.n_days - 1, Costs(10, 25))
            assert reconcile(bt) < 1e-6

    # The check has teeth: a ledger that disagrees with the engine by one cent is caught.
    assert bt.trades
    bt.trades[0]["fee"] += 0.01
    assert reconcile(bt) > 1e-3


@pytest.mark.gate
def test_known_scenarios():
    trend, meanrev, breakout = REGISTRY["trend"], REGISTRY["meanrev"], REGISTRY["breakout"]

    # (a) Constant price: trend never trades and equity stays exactly 100,000.
    flat = make_panel(np.full(400, 100.1))
    for p in trend.params_grid:
        bt = run_strategy(flat, trend, p, 0, 399, Costs(1, 5))
        assert bt.trades == []
        assert (bt.equity == 100_000.0).all()

    # (b) Steady linear uptrend (gap-free opens): long right after warm-up, positive net return.
    close = 50.0 + 0.25 * np.arange(400)
    up = make_panel(close, open_=np.concatenate(([50.0], close[:-1])))
    p = {"fast": 10, "slow": 50}
    states = trend.states(up, p)[:, 0]
    assert not states[:49].any() and states[49:].all()
    bt = run_strategy(up, trend, p, 0, 399, Costs(1, 5))
    assert bt.trades[0]["side"] == "buy" and bt.trades[0]["date"] == up.day(50)
    assert metrics(curve(bt))["total_return"] > 0

    # (c) Clean sine wave, zero costs: mean reversion trades and makes money. The lookback spans
    # one full period, so the rolling mean sits at the wave's centre.
    close = 100.0 + 10.0 * np.sin(2 * np.pi * np.arange(600) / 40)
    wave = make_panel(close, open_=np.concatenate(([close[0]], close[:-1])))
    bt = run_strategy(wave, meanrev, {"lookback": 40, "entry_z": 1.0}, 0, 599, Costs(0, 0))
    m = metrics(curve(bt))
    assert m["trades"] >= 10
    assert m["total_return"] > 0

    # (d) Flat, then one step up: breakout's first entry is the open AFTER the step's close.
    step = 150
    close = np.where(np.arange(260) < step, 100.0, 110.0)
    stepped = make_panel(close)
    for p in breakout.params_grid:
        bt = run_strategy(stepped, breakout, p, 0, 259, Costs(1, 5))
        assert bt.trades, p
        first = bt.trades[0]
        assert first["side"] == "buy" and first["date"] == stepped.day(step + 1), p
        assert first["ref_open"] == 110.0


@pytest.mark.gate
def test_no_lookahead(small_panel):
    panel = small_panel
    assert (~panel.valid).any(), "the probe should include missing bars"
    for spec in REGISTRY.values():
        for p in spec.params_grid:
            full = spec.states(panel, p)
            for cutoff in (230, 401, 650):
                assert np.array_equal(spec.states(panel.upto(cutoff), p), full[: cutoff + 1]), (spec.id, p, cutoff)

    # Engine level: garbage prices after day k leave every trade dated <= k unchanged.
    k, start, end = 450, 200, 700
    garbage = _scale_rows(panel, np.arange(panel.n_days) > k, 10.0)
    for spec in REGISTRY.values():
        p = spec.params_grid[4]
        clean = run_strategy(panel, spec, p, start, end, Costs(5, 10))
        dirty = run_strategy(garbage, spec, p, start, end, Costs(5, 10))
        early = [t for t in clean.trades if t["day"] <= k]
        assert early, spec.id
        assert early == [t for t in dirty.trades if t["day"] <= k], spec.id
        assert np.array_equal(clean.equity[: k - start + 1], dirty.equity[: k - start + 1])
        assert not np.array_equal(clean.equity, dirty.equity), "garbage must matter after k"

    # The probe has teeth: a signal that peeks one bar ahead fails it.
    leaky = Strategy(
        "leaky",
        "leaky",
        "peeks at tomorrow",
        ({},),
        "",
        lambda p: 1,
        lambda o, h, lo, c: np.concatenate((c[1:] > c[:-1], [False])),
    )
    assert not np.array_equal(leaky.states(panel.upto(400), {}), leaky.states(panel, {})[:401])


@pytest.mark.gate
def test_deterministic_replay(small_run, tmp_path):
    again = run_cli(SMALL_REQUEST, tmp_path, "again")
    first, second = file_hashes(small_run), file_hashes(again)
    assert sorted(first) == REQUIRED_FILES
    assert first == second

    # A fresh interpreter with a different hash seed (set/dict ordering) must agree too.
    req = tmp_path / "fresh.json"
    req.write_text(json.dumps(SMALL_REQUEST))
    fresh = tmp_path / "fresh"
    subprocess.run(
        [sys.executable, "-m", "quantfoundry", "run", "--request", str(req), "--out", str(fresh)],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": "12345"},
        timeout=120,
    )
    assert file_hashes(fresh) == first


@pytest.mark.gate
def test_costs_included(small_run, tmp_path):
    free = run_cli(request(**{"costs.fee_bps": 0.0, "costs.slippage_bps": 0.0}), tmp_path, "free")
    costly_results = load(small_run / "results.json")["strategies"]
    free_results = load(free / "results.json")["strategies"]
    for r in costly_results:
        for seg in ("oos_metrics", "holdout_metrics"):
            if r[seg]["trades"] > 0:
                assert r[seg]["fees_paid"] > 0 and r[seg]["slippage_paid"] > 0, (r["id"], seg)
    for r in free_results:
        for seg in ("oos_metrics", "holdout_metrics"):
            assert r[seg]["fees_paid"] == 0 and r[seg]["slippage_paid"] == 0

    # Same params over the same OOS windows (sensitivity rows): net return is strictly lower with costs.
    def sensitivity(outdir):
        rows = read_csv(outdir / "experiments.csv")
        return {(r["strategy"], r["params"]): r for r in rows if r["window"] == "sensitivity"}

    costly, zero = sensitivity(small_run), sensitivity(free)
    compared = 0
    for key, row in costly.items():
        if int(row["trades"]) > 0:
            assert float(row["total_return"]) < float(zero[key]["total_return"]), key
            assert float(row["fees_paid"]) > 0 and float(row["slippage_paid"]) > 0
            compared += 1
    assert compared >= 20

    # Reported totals equal the trade ledger.
    trades = read_csv(small_run / "trades.csv")
    for r in costly_results:
        mine = [t for t in trades if t["strategy"] == r["id"] and t["segment"] == "out_of_sample"]
        assert sum(float(t["fee"]) for t in mine) == pytest.approx(r["oos_metrics"]["fees_paid"], abs=0.01)
        assert sum(float(t["slippage_cost"]) for t in mine) == pytest.approx(
            r["oos_metrics"]["slippage_paid"], abs=0.01
        )


@pytest.mark.gate
def test_all_experiments_recorded(small_run):
    rows = read_csv(small_run / "experiments.csv")
    windows = len(load(small_run / "walkforward.json")["windows"])
    strategies = load(small_run / "manifest.json")["params"]["strategies"]
    assert windows == 3
    expected = sum(
        len(REGISTRY[s].params_grid) * windows + windows + len(REGISTRY[s].params_grid) + 1 for s in strategies
    )
    assert len(rows) == expected
    for s in strategies:
        grid = {compact(p) for p in REGISTRY[s].params_grid}
        mine = [r for r in rows if r["strategy"] == s]
        for w in range(windows):
            in_sample = [r for r in mine if r["window"] == str(w) and r["segment"] == "in_sample"]
            assert {r["params"] for r in in_sample} == grid
            assert sum(r["window"] == str(w) and r["segment"] == "out_of_sample" for r in mine) == 1
        assert {r["params"] for r in mine if r["window"] == "sensitivity"} == grid
        assert sum(r["segment"] == "holdout" for r in mine) == 1


@pytest.mark.gate
def test_rejected_strategies_visible(small_run, tmp_path):
    results = load(small_run / "results.json")
    assert [s["id"] for s in results["strategies"]] == SMALL_REQUEST["strategies"]
    for s in results["strategies"]:
        assert s["verdict"] in ("accepted", "rejected")
        if s["verdict"] == "rejected":
            assert s["reasons"] and all(isinstance(x, str) and x for x in s["reasons"])
        else:
            assert s["reasons"] == []
    summary = results["summary"]
    assert summary["accepted"] + summary["rejected"] == 3
    assert summary["rejected"] == sum(s["verdict"] == "rejected" for s in results["strategies"])
    report = (small_run / "report.md").read_text()
    for s in results["strategies"]:
        assert f"| {s['id']} | {s['verdict']} |" in report
        for reason in s["reasons"]:
            assert reason in report

    only = run_cli(request(strategies=["trend"]), tmp_path, "trend_only")
    single = load(only / "results.json")
    assert [s["id"] for s in single["strategies"]] == ["trend"]
    assert single["summary"]["accepted"] + single["summary"]["rejected"] == 1
    assert read_csv(only / "equity.csv")[0].keys() == {"date", "segment", "trend", "buyhold", "cash"}


@pytest.mark.gate
def test_holdout_sealed(small_panel, small_run, monkeypatch):
    req = SMALL_REQUEST
    h = holdout_start_index(small_panel.n_days, req["holdout_fraction"])
    holdout_start = small_panel.dates[h]
    real_select, real_holdout = protocol.select_params, protocol.evaluate_holdout
    selections, holdouts = [], []

    def spy_select(spec, panel, window, costs, hs):
        selections.append((spec.id, panel.dates[-1], panel.n_days))
        return real_select(spec, panel, window, costs, hs)

    def spy_holdout(spec, params, panel, start, costs):
        holdouts.append((spec.id, dict(params), start, len(selections)))
        return real_holdout(spec, params, panel, start, costs)

    monkeypatch.setattr(protocol, "select_params", spy_select)
    monkeypatch.setattr(protocol, "evaluate_holdout", spy_holdout)
    research = protocol.run_research(small_panel, req)
    monkeypatch.undo()

    n_windows = len(research["windows"])
    assert len(selections) == len(req["strategies"]) * n_windows
    assert all(last < holdout_start and n <= h for _, last, n in selections)
    assert sorted(c[0] for c in holdouts) == sorted(req["strategies"]), "exactly one holdout run each"
    assert all(c[2] == h for c in holdouts)
    assert all(c[3] == len(selections) for c in holdouts), "all selection finished before any holdout run"
    for sid, rows in research["walkforward"].items():
        frozen = rows[-1]["chosen_params"]
        assert next(c[1] for c in holdouts if c[0] == sid) == frozen
        assert next(e["frozen_params"] for e in research["holdout"]["evaluations"] if e["strategy"] == sid) == frozen
    assert research["checks"]["holdout"]["evaluated_once"]

    # Selection refuses data that reaches the holdout.
    with pytest.raises(HoldoutLeakError):
        real_select(REGISTRY["trend"], small_panel, Window(0, 200, 451, 452, 514), Costs(), holdout_start)

    # Garbage holdout prices change nothing in the development period, only the holdout.
    poisoned = protocol.run_research(_scale_rows(small_panel, np.arange(small_panel.n_days) >= h, 10.0), req)
    assert poisoned["walkforward"] == research["walkforward"]
    assert poisoned["sensitivity"] == research["sensitivity"]
    dev_rows = [e for e in research["experiments"] if e["segment"] != "holdout"]
    assert [e for e in poisoned["experiments"] if e["segment"] != "holdout"] == dev_rows
    assert poisoned["holdout"]["evaluations"] != research["holdout"]["evaluations"]

    # The written outputs carry the same guarantees.
    holdout_file = load(small_run / "holdout.json")
    assert holdout_file["sealed"] is True and holdout_file["selection_frozen_before_holdout"] is True
    walkforward = load(small_run / "walkforward.json")
    for e in holdout_file["evaluations"]:
        assert e["frozen_params"] == walkforward["strategies"][e["strategy"]][-1]["chosen_params"]
    assert holdout_file["span"][0] > walkforward["windows"][-1]["test_end"]  # ISO dates sort as strings
    assert holdout_file["span"][1] == load(small_run / "manifest.json")["dataset"]["end"]
