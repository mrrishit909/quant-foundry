"""Data-quality report for a long-format OHLCV frame.

Each check has status pass, warn or fail. Fail-level problems (schema, ordering, duplicates,
impossible OHLC, non-positive prices, negative or fractional volume) stop a run through
`require_pass`. Missing bars, large moves and calendar gaps are warnings: the simulator has
an explicit rule for missing bars, and large moves can be genuine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfoundry.data.ingest import COLUMNS, PRICE_COLUMNS

LARGE_MOVE = 0.25
MAX_LISTED = 20  # cap on dates listed per finding, keeps the report small
_RANK = {"pass": 0, "warn": 1, "fail": 2}


class DataQualityError(ValueError):
    """The dataset failed at least one fail-level validation check."""


def _iso(values) -> list[str]:
    return [pd.Timestamp(v).strftime("%Y-%m-%d") for v in values]


def validate(df: pd.DataFrame) -> dict:
    checks: list[dict] = []

    def add(name: str, status: str, detail) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    missing_cols = [c for c in COLUMNS if c not in df.columns]
    bad_types = [c for c in PRICE_COLUMNS + ["volume"] if c in df.columns and not pd.api.types.is_numeric_dtype(df[c])]
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        bad_types.append("date")
    if missing_cols or bad_types:
        add("schema", "fail", {"missing_columns": missing_cols, "bad_dtypes": bad_types})
        return _report(df, checks)
    add("schema", "pass", {"columns": COLUMNS})

    dates = df["date"].to_numpy()
    unsorted = int((np.diff(dates.astype("datetime64[ns]").astype(np.int64)) < 0).sum())
    add("sorted_dates", "fail" if unsorted else "pass", {"out_of_order_rows": unsorted})

    dup = df.duplicated(["date", "symbol"], keep=False)
    examples = [{"date": d, "symbol": s} for d, s in zip(_iso(df.loc[dup, "date"]), df.loc[dup, "symbol"], strict=True)]
    add(
        "duplicate_rows",
        "fail" if dup.any() else "pass",
        {"count": int(dup.sum()), "examples": examples[:MAX_LISTED]},
    )

    prices = df[PRICE_COLUMNS].to_numpy(float)
    valid = np.isfinite(prices).all(axis=1)
    o, h, lo, c = (prices[valid, i] for i in range(4))
    bad_ohlc = (lo > np.minimum(o, c)) | (h < np.maximum(o, c)) | (lo > h)
    add("ohlc_consistency", "fail" if bad_ohlc.any() else "pass", {"violations": int(bad_ohlc.sum())})

    non_positive = int((prices[valid] <= 0).any(axis=1).sum())
    add("positive_prices", "fail" if non_positive else "pass", {"violations": non_positive})

    vol = df["volume"].to_numpy(float)
    vol = vol[np.isfinite(vol)]
    bad_vol = int(((vol < 0) | (vol != np.floor(vol))).sum())
    add("non_negative_volume", "fail" if bad_vol else "pass", {"negative_or_fractional": bad_vol})

    all_dates = pd.DatetimeIndex(sorted(pd.unique(df["date"])))
    missing: dict[str, dict] = {}
    moves: list[dict] = []
    for sym, g in df.groupby("symbol", sort=True):
        ok = np.isfinite(g[PRICE_COLUMNS].to_numpy(float)).all(axis=1)
        absent = all_dates.difference(pd.DatetimeIndex(g["date"]))
        gap_dates = sorted(set(_iso(g.loc[~ok, "date"])) | set(_iso(absent)))
        if gap_dates:
            missing[sym] = {"count": len(gap_dates), "dates": gap_dates[:MAX_LISTED]}
        closes = g.loc[ok].sort_values("date")
        change = closes["close"].pct_change().to_numpy()
        for i in np.flatnonzero(np.abs(change) > LARGE_MOVE):
            moves.append({"symbol": sym, "date": _iso([closes["date"].iloc[i]])[0], "move": float(change[i])})
    add("missing_bars", "warn" if missing else "pass", {"by_symbol": missing})
    add(
        "large_moves",
        "warn" if moves else "pass",
        {"threshold": LARGE_MOVE, "count": len(moves), "examples": moves[:MAX_LISTED]},
    )

    expected = pd.bdate_range(all_dates.min(), all_dates.max()) if len(all_dates) else all_dates
    gaps = expected.difference(all_dates)
    weekend = all_dates[all_dates.dayofweek >= 5]
    add(
        "calendar_coverage",
        "warn" if len(gaps) or len(weekend) else "pass",
        {
            "calendar_days": len(all_dates),
            "missing_business_days": len(gaps),
            "missing_examples": _iso(gaps[:MAX_LISTED]),
            "weekend_dates": _iso(weekend[:MAX_LISTED]),
        },
    )
    return _report(df, checks)


def _report(df: pd.DataFrame, checks: list[dict]) -> dict:
    status = max((c["status"] for c in checks), key=_RANK.__getitem__)
    symbols = sorted(df["symbol"].dropna().unique().tolist()) if "symbol" in df.columns else []
    return {"status": status, "rows": len(df), "symbols": symbols, "checks": checks}


def require_pass(report: dict) -> None:
    failed = [c["name"] for c in report["checks"] if c["status"] == "fail"]
    if failed:
        raise DataQualityError(f"data validation failed: {', '.join(failed)}")
