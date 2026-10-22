"""Strategy registry: three long-only daily strategies with bounded parameter grids.

A signal function receives one symbol's VALID bars only (missing bars removed) and returns
the desired state (True = long, False = flat) at each bar's close. Every value at bar t is
computed from bars 0..t: rolling statistics use windows ending at t, and anything described
as "previous N bars" is shifted by one bar. `Strategy.states` maps the result back onto the
full calendar and carries the last state across missing bars.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from quantfoundry.data.panel import Panel

SIGNAL_TIMING = (
    "computed from bars up to and including the close of day t; the resulting order fills at the open of day t+1"
)


def _rolling(x: np.ndarray, n: int, fn, **kwargs) -> np.ndarray:
    """Statistic over the window of n bars ending at each bar; NaN until n bars exist."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1 :] = fn(sliding_window_view(x, n), axis=1, **kwargs)
    return out


def _shift(x: np.ndarray) -> np.ndarray:
    return np.concatenate(([np.nan], x[:-1]))


def trend_signal(o, h, lo, c, *, fast: int, slow: int) -> np.ndarray:
    # Rounding removes float noise so a constant price never yields a spurious fast > slow.
    fast_ma = np.round(_rolling(c, fast, np.mean), 8)
    slow_ma = np.round(_rolling(c, slow, np.mean), 8)
    return fast_ma > slow_ma


def meanrev_signal(o, h, lo, c, *, lookback: int, entry_z: float) -> np.ndarray:
    mean = _rolling(c, lookback, np.mean)
    std = _rolling(c, lookback, np.std, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(std > 1e-9 * np.abs(mean), (c - mean) / std, np.nan)
    state = np.zeros(len(c), dtype=bool)
    long = False
    for t in range(len(c)):
        if not long and z[t] < -entry_z:
            long = True
        elif long and z[t] >= 0:
            long = False
        state[t] = long
    return state


def breakout_signal(o, h, lo, c, *, N: int, k: float) -> np.ndarray:
    prev_close = _shift(c)
    true_range = np.fmax(h - lo, np.fmax(np.abs(h - prev_close), np.abs(lo - prev_close)))
    atr_prior = _shift(_rolling(true_range, N, np.mean))
    upper = _shift(_rolling(h, N, np.max)) + k * atr_prior
    lower = _shift(_rolling(lo, N // 2, np.min))
    state = np.zeros(len(c), dtype=bool)
    long = False
    for t in range(len(c)):
        if not long and c[t] > upper[t]:
            long = True
        elif long and c[t] < lower[t]:
            long = False
        state[t] = long
    return state


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    description: str
    params_grid: tuple[dict, ...]
    warmup_rule: str
    warmup_bars: Callable[[dict], int]
    signal: Callable[..., np.ndarray]
    signal_timing: str = SIGNAL_TIMING

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "params_grid": [dict(p) for p in self.params_grid],
            "warmup_rule": self.warmup_rule,
            "signal_timing": self.signal_timing,
            "long_only": True,
        }

    def states(self, panel: Panel, params: dict) -> np.ndarray:
        """Desired long/flat state per (day, symbol) at each close; flat before warm-up."""
        out = np.zeros(panel.close.shape, dtype=bool)
        valid = panel.valid
        for j in range(panel.n_symbols):
            rows = np.flatnonzero(valid[:, j])
            if rows.size == 0:
                continue
            sig = self.signal(
                panel.open[rows, j], panel.high[rows, j], panel.low[rows, j], panel.close[rows, j], **params
            )
            last_valid = np.cumsum(valid[:, j]) - 1
            out[:, j] = np.where(last_valid >= 0, sig[np.maximum(last_valid, 0)], False)
        return out


REGISTRY: dict[str, Strategy] = {
    s.id: s
    for s in (
        Strategy(
            id="trend",
            name="Trend following (SMA crossover)",
            description="Long while SMA(fast) of closes is above SMA(slow), otherwise flat.",
            params_grid=tuple({"fast": f, "slow": s} for f in (10, 20, 40) for s in (50, 100, 200) if f < s),
            warmup_rule="slow bars: SMA(slow) needs slow closes",
            warmup_bars=lambda p: p["slow"],
            signal=trend_signal,
        ),
        Strategy(
            id="meanrev",
            name="Mean reversion (z-score)",
            description=(
                "z = (close - rolling mean) / rolling std over lookback closes. Enter long when "
                "z < -entry_z, exit when z >= 0."
            ),
            params_grid=tuple({"lookback": n, "entry_z": z} for n in (10, 20, 40) for z in (1.0, 1.5, 2.0)),
            warmup_rule="lookback bars: rolling mean and std need lookback closes",
            warmup_bars=lambda p: p["lookback"],
            signal=meanrev_signal,
        ),
        Strategy(
            id="breakout",
            name="Volatility breakout",
            description=(
                "Enter long when close > highest high of the previous N bars + k * ATR(N) of the "
                "previous N bars. Exit when close < lowest low of the previous N // 2 bars."
            ),
            params_grid=tuple({"N": n, "k": k} for n in (20, 55, 100) for k in (0.0, 0.5, 1.0)),
            warmup_rule="N + 1 bars: channel and ATR use the N bars before the signal bar",
            warmup_bars=lambda p: p["N"] + 1,
            signal=breakout_signal,
        ),
    )
}


def get_strategy(strategy_id: str) -> Strategy:
    if strategy_id not in REGISTRY:
        raise ValueError(f"unknown strategy {strategy_id!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[strategy_id]


def params_key(params: dict) -> tuple:
    """Lexicographic sort key over a params dict (keys in sorted order)."""
    return tuple(params[k] for k in sorted(params))
