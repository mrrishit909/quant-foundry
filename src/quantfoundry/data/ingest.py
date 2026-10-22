"""Bounded CSV ingestion and canonicalization.

Every dataset, synthetic or file-based, is reduced to the same canonical CSV bytes
(sorted by date then symbol, ISO dates, prices with 4 decimals, integer volume, missing
values as empty fields). The dataset hash is the sha256 of those bytes, and the frame
handed to the simulator is parsed back from them, so the hash describes exactly the data
that was traded.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close"]
CANONICAL_TRANSFORMATIONS = [
    "sorted rows by (date, symbol)",
    "formatted dates as YYYY-MM-DD",
    "rounded prices to 4 decimals",
    "cast volume to integer",
    "wrote missing values as empty fields",
]


@dataclass(frozen=True)
class Limits:
    max_symbols: int = 10
    max_rows: int = 30_000
    max_bytes: int = 5_000_000


class IngestError(ValueError):
    """Input file is malformed or exceeds the ingestion bounds."""


def canonical_csv_bytes(df: pd.DataFrame) -> bytes:
    out = df[COLUMNS].sort_values(["date", "symbol"], kind="mergesort").copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["volume"] = out["volume"].round().astype("Int64")
    return out.to_csv(index=False, float_format="%.4f", lineterminator="\n").encode("utf-8")


def _parse(data: bytes) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.BytesIO(data), dtype={"symbol": str})
    except (ValueError, pd.errors.ParserError) as exc:
        raise IngestError(f"could not parse CSV: {exc}") from exc
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise IngestError(f"missing required columns: {missing}")
    df = df[COLUMNS].copy()
    try:
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
        for col in PRICE_COLUMNS + ["volume"]:
            df[col] = pd.to_numeric(df[col]).astype(float)
    except (ValueError, TypeError) as exc:
        raise IngestError(f"bad date or numeric value: {exc}") from exc
    return df


def ingest_bytes(
    data: bytes,
    *,
    source: str,
    retrieval_date: str | None = None,
    limits: Limits = Limits(),  # noqa: B008  (frozen dataclass, safe as a default)
    transformations: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, dict, bytes]:
    """Bound-check, canonicalize and hash raw CSV bytes. Returns (frame, manifest, canonical bytes)."""
    if len(data) > limits.max_bytes:
        raise IngestError(f"input is {len(data)} bytes; the limit is {limits.max_bytes}")
    raw = _parse(data)
    if len(raw) > limits.max_rows:
        raise IngestError(f"input has {len(raw)} rows; the limit is {limits.max_rows}")
    n_symbols = raw["symbol"].nunique()
    if n_symbols > limits.max_symbols:
        raise IngestError(f"input has {n_symbols} symbols; the limit is {limits.max_symbols}")
    if raw["symbol"].isna().any() or raw["date"].isna().any():
        raise IngestError("every row needs a date and a symbol")

    canonical = canonical_csv_bytes(raw)
    df = _parse(canonical)
    manifest = {
        "source": source,
        "retrieval_date": retrieval_date,
        "coverage": {
            "start": df["date"].min().strftime("%Y-%m-%d"),
            "end": df["date"].max().strftime("%Y-%m-%d"),
            "symbols": sorted(df["symbol"].unique().tolist()),
            "rows": len(df),
        },
        "transformations": list(transformations) + CANONICAL_TRANSFORMATIONS,
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
    return df, manifest, canonical


def ingest_csv(
    path: str | Path,
    limits: Limits = Limits(),  # noqa: B008
    retrieval_date: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    path = Path(path)
    size = path.stat().st_size
    if size > limits.max_bytes:
        raise IngestError(f"{path.name} is {size} bytes; the limit is {limits.max_bytes}")
    df, manifest, _ = ingest_bytes(
        path.read_bytes(),
        source=f"file:{path.name}",
        retrieval_date=retrieval_date,
        limits=limits,
        transformations=(f"read {path.name}",),
    )
    return df, manifest
