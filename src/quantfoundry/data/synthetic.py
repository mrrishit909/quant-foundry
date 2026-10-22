"""Deterministic synthetic daily OHLCV generator (the only data source of the public demo).

Calendar assumption: pandas.bdate_range starting 2015-01-02, Monday to Friday, with no
exchange holidays. Real exchanges close on holidays; this dataset does not model them.

Each symbol's history is cut into segments of 63-252 bars. Every segment draws one regime:
trending (drift plus AR(1) momentum in returns), mean-reverting (Ornstein-Uhlenbeck pull of
log price toward the segment's starting level) or volatility clustering (GARCH(1,1) variance).
Occasional jumps are added in every regime. `regime_mix` sets the regime probabilities.

Defects: 1-3 missing bars (all OHLCV fields NaN) are injected into one symbol so that data
validation and the simulator's missing-data rule are exercised on every run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CALENDAR_START = "2015-01-02"
CALENDAR_NOTE = (
    "synthetic business days: pandas.bdate_range starting 2015-01-02, Monday to Friday, no exchange holidays"
)
# Probabilities of (trending, mean-reverting, volatility-clustering) segments.
REGIME_MIX = {
    "balanced": (0.34, 0.33, 0.33),
    "trending": (0.70, 0.15, 0.15),
    "choppy": (0.15, 0.70, 0.15),
    "volatile": (0.15, 0.15, 0.70),
}
TREND, MEANREV = 0, 1
JUMP_PROB = 0.004
MIN_LOW = 5.0
FIELDS = ("open", "high", "low", "close", "volume")


def symbol_names(n: int) -> list[str]:
    return [f"SYN{i:02d}" for i in range(1, n + 1)]


def generate(seed: int, symbols: int, days: int, regime_mix: str) -> tuple[pd.DataFrame, list[dict]]:
    """Return (long-format OHLCV frame sorted by date then symbol, injected defects)."""
    if not 2 <= symbols <= 10:
        raise ValueError(f"symbols must be between 2 and 10, got {symbols}")
    if not 756 <= days <= 2520:
        raise ValueError(f"days must be between 756 and 2520, got {days}")
    if regime_mix not in REGIME_MIX:
        raise ValueError(f"regime_mix must be one of {sorted(REGIME_MIX)}, got {regime_mix!r}")

    rng = np.random.Generator(np.random.PCG64(seed))
    dates = pd.bdate_range(CALENDAR_START, periods=days)
    names = symbol_names(symbols)
    wide = {f: np.empty((days, symbols)) for f in FIELDS}
    for j in range(symbols):
        for field, values in zip(FIELDS, _symbol_bars(rng, days, REGIME_MIX[regime_mix]), strict=True):
            wide[field][:, j] = values
    defects = _inject_missing_bars(rng, wide, dates, names)

    frame = pd.DataFrame(
        {
            "date": np.repeat(dates.values, symbols),
            "symbol": np.tile(names, days),
            **{f: wide[f].reshape(-1) for f in FIELDS},
        }
    )
    return frame, defects


def _symbol_bars(rng: np.random.Generator, days: int, mix: tuple[float, ...]) -> tuple[np.ndarray, ...]:
    start_price = rng.uniform(20.0, 200.0)
    base_volume = rng.uniform(2e5, 2e6)
    z = rng.standard_normal((5, days))
    jumps = np.where(rng.random(days) < JUMP_PROB, rng.normal(0.0, 0.06, days), 0.0)

    log_close = np.empty(days)
    sigma_t = np.empty(days)
    x = np.log(start_price)
    r_prev = 0.0
    t = 0
    while t < days:
        end = min(days, t + int(rng.integers(63, 253)))
        kind = int(rng.choice(3, p=mix))
        sigma = rng.uniform(0.008, 0.02)
        drift = rng.uniform(0.0004, 0.0015) * (1.0 if rng.random() < 0.6 else -1.0)
        level = x
        var = (1.8 * sigma) ** 2  # GARCH long-run variance: volatile segments run hotter
        omega = var * (1.0 - 0.10 - 0.85)
        for i in range(t, end):
            if kind == TREND:
                s = sigma
                r = drift + 0.15 * r_prev + s * z[0, i]
            elif kind == MEANREV:
                s = sigma
                r = 0.08 * (level - x) + s * z[0, i]
            else:
                var = omega + 0.10 * r_prev**2 + 0.85 * var
                s = float(np.sqrt(var))
                r = s * z[0, i]
            r += jumps[i]
            x += r
            log_close[i] = x
            sigma_t[i] = s
            r_prev = r
        t = end

    close = np.exp(log_close)
    prev_close = np.concatenate(([start_price], close[:-1]))
    open_ = prev_close * np.exp(0.3 * sigma_t * z[1])
    high = np.maximum(open_, close) * np.exp(0.5 * sigma_t * np.abs(z[2]))
    low = np.minimum(open_, close) * np.exp(-0.5 * sigma_t * np.abs(z[3]))
    # Rescaling a whole series leaves every return unchanged; it keeps prices far from 0 so that
    # 4-decimal canonical rounding does not distort them. The scale only looks at bars that can
    # never be holdout (the schema's largest holdout_fraction is 0.3), so holdout prices cannot
    # change development-period data. Later bars may therefore dip below MIN_LOW.
    never_holdout = days - (3 * days) // 10
    scale = max(1.0, MIN_LOW / low[:never_holdout].min())
    move = np.abs(np.log(close / prev_close)) / sigma_t
    volume = np.floor(base_volume * np.exp(0.25 * z[4]) * (1.0 + move))
    return open_ * scale, high * scale, low * scale, close * scale, volume


def _inject_missing_bars(
    rng: np.random.Generator, wide: dict[str, np.ndarray], dates: pd.DatetimeIndex, names: list[str]
) -> list[dict]:
    count = int(rng.integers(1, 4))
    j = int(rng.integers(len(names)))
    rows = np.sort(rng.choice(np.arange(20, len(dates) - 20), size=count, replace=False))
    for values in wide.values():
        values[rows, j] = np.nan
    return [{"kind": "missing_bar", "symbol": names[j], "date": dates[r].strftime("%Y-%m-%d")} for r in rows]
