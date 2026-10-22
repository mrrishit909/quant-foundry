"""Synthetic generator, bounded ingestion and data validation."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantfoundry.data import synthetic
from quantfoundry.data.ingest import IngestError, Limits, canonical_csv_bytes, ingest_bytes, ingest_csv
from quantfoundry.data.validate import DataQualityError, require_pass, validate


def _canonical(seed=3, symbols=4, days=800, mix="balanced"):
    frame, defects = synthetic.generate(seed, symbols, days, mix)
    return canonical_csv_bytes(frame), frame, defects


def test_generator_is_deterministic():
    a, _, da = _canonical(seed=5)
    b, _, db = _canonical(seed=5)
    c, _, _ = _canonical(seed=6)
    assert a == b and da == db
    assert a != c
    for mix in synthetic.REGIME_MIX:
        assert _canonical(seed=5, mix=mix)[0] == _canonical(seed=5, mix=mix)[0]


@pytest.mark.parametrize("mix", sorted(synthetic.REGIME_MIX))
def test_generator_bars_are_valid(mix):
    raw, _, _ = _canonical(seed=9, symbols=10, days=2520, mix=mix)
    df, _, _ = ingest_bytes(raw, source="test")
    ok = df[["open", "high", "low", "close"]].notna().all(axis=1)
    bars = df[ok]
    assert (bars["low"] <= bars[["open", "close"]].min(axis=1)).all()
    assert (bars["high"] >= bars[["open", "close"]].max(axis=1)).all()
    assert (bars[["open", "high", "low", "close"]] > 0).all().all()
    assert (bars["volume"] >= 0).all() and (bars["volume"] == bars["volume"].round()).all()
    assert validate(df)["status"] in ("pass", "warn")


def test_generator_calendar_names_and_defects():
    frame, defects = synthetic.generate(1, 4, 756, "trending")
    dates = pd.DatetimeIndex(sorted(frame["date"].unique()))
    assert dates[0] == pd.Timestamp("2015-01-02") and len(dates) == 756
    assert (dates.dayofweek < 5).all()
    assert len(pd.bdate_range(dates[0], dates[-1])) == 756  # no gaps: no holidays modelled
    assert sorted(frame["symbol"].unique()) == ["SYN01", "SYN02", "SYN03", "SYN04"]
    assert 1 <= len(defects) <= 3 and len({d["symbol"] for d in defects}) == 1
    nan_rows = frame[frame["close"].isna()]
    assert sorted(zip(nan_rows["symbol"], nan_rows["date"].dt.strftime("%Y-%m-%d"), strict=True)) == sorted(
        (d["symbol"], d["date"]) for d in defects
    )
    assert nan_rows[["open", "high", "low", "volume"]].isna().all().all()


@pytest.mark.parametrize(
    ("symbols", "days", "mix"),
    [(1, 756, "balanced"), (11, 756, "balanced"), (3, 755, "balanced"), (3, 2521, "balanced"), (3, 756, "sideways")],
)
def test_generator_rejects_out_of_bounds(symbols, days, mix):
    with pytest.raises(ValueError):
        synthetic.generate(1, symbols, days, mix)


def test_generator_scale_window_matches_schema_max_holdout():
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "request.schema.json").read_text())
    # synthetic._symbol_bars rescales from bars before days - floor(0.3 * days)
    assert schema["properties"]["holdout_fraction"]["maximum"] == 0.3


def test_ingest_canonicalizes_and_hashes(tmp_path):
    raw, frame, _ = _canonical()
    df, manifest, canonical = ingest_bytes(raw, source="synthetic:test", transformations=("generated",))
    assert canonical == raw == canonical_csv_bytes(df)  # canonical form is a fixed point
    assert manifest["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["coverage"]["rows"] == len(frame) and manifest["coverage"]["start"] == "2015-01-02"
    assert manifest["transformations"][0] == "generated"

    # A shuffled file with more decimals canonicalizes to the same bytes and hash.
    messy = frame.sample(frac=1.0, random_state=0)
    path = tmp_path / "messy.csv"
    messy.assign(date=messy["date"].dt.strftime("%Y-%m-%d")).to_csv(path, index=False)
    df2, manifest2 = ingest_csv(path, retrieval_date="2026-10-21")
    assert manifest2["sha256"] == manifest["sha256"]
    assert manifest2["retrieval_date"] == "2026-10-21" and manifest2["source"] == "file:messy.csv"
    pd.testing.assert_frame_equal(df2, df)


def test_ingest_enforces_bounds(tmp_path):
    raw, _, _ = _canonical(symbols=4, days=800)
    with pytest.raises(IngestError, match="symbols"):
        ingest_bytes(raw, source="t", limits=Limits(max_symbols=3))
    with pytest.raises(IngestError, match="rows"):
        ingest_bytes(raw, source="t", limits=Limits(max_rows=3199))
    with pytest.raises(IngestError, match="bytes"):
        ingest_bytes(raw, source="t", limits=Limits(max_bytes=len(raw) - 1))
    big = tmp_path / "big.csv"
    big.write_bytes(raw + b"x" * 5_000_001)
    with pytest.raises(IngestError, match="limit is 5000000"):
        ingest_csv(big)
    with pytest.raises(IngestError, match="missing required columns"):
        ingest_bytes(b"date,symbol,open\n2015-01-02,A,1\n", source="t")
    with pytest.raises(IngestError, match="bad date or numeric"):
        ingest_bytes(b"date,symbol,open,high,low,close,volume\n2015-01-02,A,x,1,1,1,1\n", source="t")


def _good_frame():
    dates = pd.bdate_range("2020-01-01", periods=10)
    rows = []
    for sym in ("AAA", "BBB"):
        for i, d in enumerate(dates):
            c = 100.0 + i
            rows.append(
                {"date": d, "symbol": sym, "open": c - 0.5, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0}
            )
    return pd.DataFrame(rows).sort_values(["date", "symbol"]).reset_index(drop=True)


def _status(df, name):
    return next(c for c in validate(df)["checks"] if c["name"] == name)


def test_validate_passes_clean_frame():
    report = validate(_good_frame())
    assert report["status"] == "pass"
    require_pass(report)


def test_validate_each_check_fires():
    good = _good_frame()

    assert _status(good.drop(columns="volume"), "schema")["status"] == "fail"
    assert _status(good.assign(close=good["close"].astype(str)), "schema")["status"] == "fail"
    assert _status(good.iloc[::-1].reset_index(drop=True), "sorted_dates")["status"] == "fail"
    assert _status(pd.concat([good, good.iloc[[3]]]).sort_values("date"), "duplicate_rows")["status"] == "fail"

    bad = good.copy()
    bad.loc[4, "high"] = bad.loc[4, "close"] - 5
    assert _status(bad, "ohlc_consistency")["status"] == "fail"

    bad = good.copy()
    bad.loc[5, ["open", "high", "low", "close"]] = [-1.0, 1.0, -2.0, -1.0]
    assert _status(bad, "positive_prices")["status"] == "fail"

    bad = good.copy()
    bad.loc[6, "volume"] = -10
    assert _status(bad, "non_negative_volume")["status"] == "fail"
    bad.loc[6, "volume"] = 10.5
    assert _status(bad, "non_negative_volume")["status"] == "fail"

    bad = good.copy()
    bad.loc[7, ["open", "high", "low", "close", "volume"]] = np.nan
    gap = good.drop(index=8)
    missing = _status(bad, "missing_bars")
    assert missing["status"] == "warn"
    assert missing["detail"]["by_symbol"] == {"BBB": {"count": 1, "dates": ["2020-01-06"]}}
    assert _status(gap, "missing_bars")["detail"]["by_symbol"]["AAA"]["count"] == 1

    bad = good.copy()
    bad.loc[bad["symbol"] == "AAA", ["open", "high", "low", "close"]] *= np.where(np.arange(10) >= 5, 1.4, 1.0)[:, None]
    jump = _status(bad, "large_moves")
    assert jump["status"] == "warn" and jump["detail"]["examples"][0]["symbol"] == "AAA"

    holes = good[good["date"] != good["date"].unique()[4]]
    assert _status(holes, "calendar_coverage")["status"] == "warn"
    weekend = good.copy()
    weekend.loc[0, "date"] = pd.Timestamp("2019-12-28")
    assert _status(weekend.sort_values("date"), "calendar_coverage")["detail"]["weekend_dates"] == ["2019-12-28"]


def test_require_pass_stops_on_fail():
    bad = _good_frame()
    bad.loc[2, "low"] = bad.loc[2, "high"] + 1
    with pytest.raises(DataQualityError, match="ohlc_consistency"):
        require_pass(validate(bad))
