"""Wide (dates x symbols) price arrays used by strategies and the simulator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Panel:
    dates: pd.DatetimeIndex
    symbols: tuple[str, ...]
    open: np.ndarray  # shape (days, symbols); NaN marks a missing bar
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> Panel:
        symbols = tuple(sorted(df["symbol"].unique()))
        wide = df.pivot(index="date", columns="symbol").sort_index()

        def field(name: str) -> np.ndarray:
            return wide[name].reindex(columns=list(symbols)).to_numpy(dtype=float)

        return cls(
            pd.DatetimeIndex(wide.index),
            symbols,
            field("open"),
            field("high"),
            field("low"),
            field("close"),
            field("volume"),
        )

    @property
    def n_days(self) -> int:
        return len(self.dates)

    @property
    def n_symbols(self) -> int:
        return len(self.symbols)

    @property
    def valid(self) -> np.ndarray:
        """True where the bar exists (all of open, high, low, close are finite)."""
        return np.isfinite(self.open) & np.isfinite(self.high) & np.isfinite(self.low) & np.isfinite(self.close)

    def upto(self, end: int) -> Panel:
        """Rows 0..end inclusive: everything a decision at the close of day `end` may see."""
        s = slice(0, end + 1)
        return Panel(
            self.dates[s], self.symbols, self.open[s], self.high[s], self.low[s], self.close[s], self.volume[s]
        )

    def day(self, i: int) -> str:
        return self.dates[i].strftime("%Y-%m-%d")
