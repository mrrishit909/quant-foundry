"""Performance metrics on daily return curves (single backtests or stitched segments)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from quantfoundry.sim.engine import Backtest

TRADING_DAYS = 252
METRIC_KEYS = [
    "total_return",
    "cagr",
    "volatility",
    "sharpe",
    "max_drawdown",
    "trades",
    "turnover",
    "fees_paid",
    "slippage_paid",
    "exposure",
]


@dataclass(frozen=True)
class Curve:
    returns: np.ndarray  # daily simple returns, first day measured against starting cash
    exposure: np.ndarray  # gross weight at each close
    turnover: np.ndarray  # traded notional / previous close equity
    trades: int
    fees: float
    slippage: float


def curve(bt: Backtest) -> Curve:
    prev = np.concatenate(([bt.initial_cash], bt.equity[:-1]))
    traded = np.zeros(len(bt.equity))
    for tr in bt.trades:
        traded[tr["day"] - bt.start] += tr["notional"]
    return Curve(
        returns=bt.equity / prev - 1.0,
        exposure=bt.market_value / bt.equity,
        turnover=traded / prev,
        trades=len(bt.trades),
        fees=float(sum(tr["fee"] for tr in bt.trades)),
        slippage=float(sum(tr["slippage_cost"] for tr in bt.trades)),
    )


def stitch(curves: list[Curve]) -> Curve:
    """Chain segments: returns are concatenated, money totals are summed over segments."""
    return Curve(
        returns=np.concatenate([c.returns for c in curves]),
        exposure=np.concatenate([c.exposure for c in curves]),
        turnover=np.concatenate([c.turnover for c in curves]),
        trades=sum(c.trades for c in curves),
        fees=sum(c.fees for c in curves),
        slippage=sum(c.slippage for c in curves),
    )


def growth(c: Curve) -> np.ndarray:
    return np.cumprod(1.0 + c.returns)


def metrics(c: Curve) -> dict:
    r = c.returns
    n = len(r)
    g = growth(c)
    final = float(g[-1]) if n else 1.0
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    path = np.concatenate(([1.0], g))
    drawdown = path / np.maximum.accumulate(path) - 1.0
    return {
        "total_return": final - 1.0,
        "cagr": (final ** (TRADING_DAYS / n) - 1.0 if final > 0 else -1.0) if n else 0.0,
        "volatility": sd * math.sqrt(TRADING_DAYS),
        # std below 1e-12 means a flat curve (exact zeros up to float noise): Sharpe 0.
        "sharpe": float(r.mean()) / sd * math.sqrt(TRADING_DAYS) if sd > 1e-12 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "trades": int(c.trades),
        "turnover": float(c.turnover.sum()),
        "fees_paid": float(c.fees),
        "slippage_paid": float(c.slippage),
        "exposure": float(c.exposure.mean()) if n else 0.0,
    }
