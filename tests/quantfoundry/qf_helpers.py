"""Shared helpers for the quantfoundry tests (imported by name; this directory has no __init__)."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantfoundry.cli import main
from quantfoundry.data import synthetic
from quantfoundry.data.ingest import canonical_csv_bytes, ingest_bytes
from quantfoundry.data.panel import Panel

DEFAULT_REQUEST = {
    "dataset": {"kind": "synthetic", "seed": 7, "symbols": 6, "days": 1512, "regime_mix": "balanced"},
    "strategies": ["trend", "meanrev", "breakout"],
    "costs": {"fee_bps": 1.0, "slippage_bps": 5.0},
    "walk_forward": {"train_days": 504, "test_days": 126},
    "holdout_fraction": 0.2,
    "allow_short": False,
}
# Smallest request the schema allows that still gives 3 walk-forward windows.
SMALL_REQUEST = {
    "dataset": {"kind": "synthetic", "seed": 11, "symbols": 3, "days": 756, "regime_mix": "balanced"},
    "strategies": ["trend", "meanrev", "breakout"],
    "costs": {"fee_bps": 10.0, "slippage_bps": 25.0},
    "walk_forward": {"train_days": 252, "test_days": 63},
    "holdout_fraction": 0.1,
    "allow_short": False,
}


def request(base: dict = SMALL_REQUEST, **changes) -> dict:
    """Deep copy of `base` with dotted-path overrides, e.g. request(**{"costs.fee_bps": 0.0})."""
    out = copy.deepcopy(base)
    for path, value in changes.items():
        node = out
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return out


def run_cli(req: dict, workdir: Path, name: str) -> Path:
    req_path = workdir / f"{name}.json"
    req_path.write_text(json.dumps(req))
    out = workdir / name
    assert main(["run", "--request", str(req_path), "--out", str(out)]) == 0
    return out


def synthetic_panel(seed: int = 11, symbols: int = 3, days: int = 756, mix: str = "balanced") -> Panel:
    frame, _ = synthetic.generate(seed, symbols, days, mix)
    df, _, _ = ingest_bytes(canonical_csv_bytes(frame), source="test")
    return Panel.from_frame(df)


def make_panel(close, open_=None, high=None, low=None) -> Panel:
    close = np.asarray(close, dtype=float)
    if close.ndim == 1:
        close = close[:, None]
    open_ = close.copy() if open_ is None else np.asarray(open_, dtype=float).reshape(close.shape)
    high = np.maximum(open_, close) if high is None else np.asarray(high, dtype=float).reshape(close.shape)
    low = np.minimum(open_, close) if low is None else np.asarray(low, dtype=float).reshape(close.shape)
    days, n = close.shape
    return Panel(
        pd.bdate_range("2015-01-02", periods=days),
        tuple(f"T{j:02d}" for j in range(n)),
        open_,
        high,
        low,
        close,
        np.full(close.shape, 1000.0),
    )


def random_panel(rng: np.random.Generator, days: int, n: int, missing: int = 3) -> Panel:
    """Random-walk OHLC with `missing` NaN bars scattered over random symbols."""
    close = 50.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, (days, n)), axis=0))
    prev = np.vstack([np.full(n, 50.0), close[:-1]])
    open_ = prev * np.exp(rng.normal(0.0, 0.005, (days, n)))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    for _ in range(missing):
        t, j = int(rng.integers(days)), int(rng.integers(n))
        for a in (open_, high, low, close):
            a[t, j] = np.nan
    return make_panel(close, open_, high, low)


def file_hashes(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
