"""Command line: `python -m quantfoundry run --request REQUEST.json --out OUTDIR` and `validate OUTDIR`."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import jsonschema

from quantfoundry import __version__, outputs
from quantfoundry.data import synthetic
from quantfoundry.data.ingest import canonical_csv_bytes, ingest_bytes
from quantfoundry.data.panel import Panel
from quantfoundry.data.validate import DataQualityError, require_pass, validate
from quantfoundry.research.protocol import SHORT_ERROR, ProtocolError, assumptions, run_research
from quantfoundry.strategies import REGISTRY

SCHEMA_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "schemas" / "request.schema.json",
    Path.cwd() / "schemas" / "request.schema.json",
)
# (path, minimum, maximum); mirrors schemas/request.schema.json so bounds hold without the schema.
BOUNDS = (
    (("dataset", "seed"), 0, 2**31 - 1),
    (("dataset", "symbols"), 2, 10),
    (("dataset", "days"), 756, 2520),
    (("costs", "fee_bps"), 0, 50),
    (("costs", "slippage_bps"), 0, 100),
    (("walk_forward", "train_days"), 252, 756),
    (("walk_forward", "test_days"), 63, 252),
    (("holdout_fraction",), 0.1, 0.3),
)
INTEGER_PATHS = {
    ("dataset", "seed"),
    ("dataset", "symbols"),
    ("dataset", "days"),
    ("walk_forward", "train_days"),
    ("walk_forward", "test_days"),
}


class RequestError(ValueError):
    """The request is malformed or outside the allowed bounds."""


def check_request(params: dict) -> None:
    """Code-level re-check of the request bounds (independent of the JSON schema)."""
    if not isinstance(params, dict):
        raise RequestError("request must be a JSON object")
    if params.get("allow_short") is not False:
        raise RequestError(SHORT_ERROR if params.get("allow_short") is True else "allow_short must be false")
    if params.get("dataset", {}).get("kind") != "synthetic":
        raise RequestError("dataset.kind must be 'synthetic' (the public demo uses synthetic data only)")
    if params["dataset"].get("regime_mix") not in synthetic.REGIME_MIX:
        raise RequestError(f"dataset.regime_mix must be one of {sorted(synthetic.REGIME_MIX)}")
    for path, lo, hi in BOUNDS:
        value = params
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        name = ".".join(path)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RequestError(f"{name} must be a number")
        if path in INTEGER_PATHS and not isinstance(value, int):
            raise RequestError(f"{name} must be an integer")
        if not lo <= value <= hi:
            raise RequestError(f"{name}={value} is outside [{lo}, {hi}]")
    strategies = params.get("strategies")
    if not isinstance(strategies, list) or not 1 <= len(strategies) <= 3 or len(set(strategies)) != len(strategies):
        raise RequestError("strategies must be a list of 1-3 distinct strategy ids")
    unknown = [s for s in strategies if s not in REGISTRY]
    if unknown:
        raise RequestError(f"unknown strategies {unknown}; known: {sorted(REGISTRY)}")


def load_request(path: Path, schema_path: Path | None = None) -> dict:
    try:
        params = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RequestError(f"cannot read request {path}: {exc}") from exc
    if isinstance(params, dict) and params.get("allow_short") is True:
        raise RequestError(SHORT_ERROR)  # clearer than the schema's "False was expected"
    if schema_path is None:
        schema_path = next((p for p in SCHEMA_CANDIDATES if p.is_file()), None)
        if schema_path is None:
            raise RequestError("schemas/request.schema.json not found; pass --schema")
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(params), key=lambda e: list(e.path))
    if errors:
        raise RequestError("; ".join(f"{'.'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:5]))
    check_request(params)
    return params


def run(request_path: Path, outdir: Path, schema_path: Path | None = None) -> dict:
    params = load_request(request_path, schema_path)
    if outdir.exists() and (not outdir.is_dir() or any(outdir.iterdir())):
        raise RequestError(f"output directory {outdir} must be empty or not exist")

    ds = params["dataset"]
    frame, defects = synthetic.generate(ds["seed"], ds["symbols"], ds["days"], ds["regime_mix"])
    data, source_manifest, canonical = ingest_bytes(
        canonical_csv_bytes(frame),
        source=f"synthetic:seed={ds['seed']},symbols={ds['symbols']},days={ds['days']},regime_mix={ds['regime_mix']}",
        transformations=("generated in-process by quantfoundry.data.synthetic (numpy PCG64)",),
    )
    quality = validate(data)
    require_pass(quality)
    research = run_research(Panel.from_frame(data), params)

    sha = source_manifest["sha256"]
    identity = outputs.compact({"params": params, "dataset_sha256": sha, "package_version": __version__})
    manifest = {
        "params": params,
        "dataset": {
            **ds,
            "sha256": sha,
            "rows": source_manifest["coverage"]["rows"],
            "start": source_manifest["coverage"]["start"],
            "end": source_manifest["coverage"]["end"],
            "calendar": synthetic.CALENDAR_NOTE,
            "injected_defects": defects,
        },
        "source_manifest": source_manifest,
        "package_version": __version__,
        "input_manifest_hash": "sha256:" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
    }
    outputs.write_run(
        outdir,
        manifest=manifest,
        dataset_csv=canonical,
        quality=quality,
        strategies=[s.snapshot() for s in REGISTRY.values()],
        assumptions=assumptions(research["costs"]),
        research=research,
    )
    return research["summary"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quantfoundry", description="Quant Foundry research engine")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run the research protocol for one request")
    run_p.add_argument("--request", required=True, type=Path)
    run_p.add_argument("--out", required=True, type=Path)
    run_p.add_argument("--schema", type=Path, default=None)
    val_p = sub.add_parser("validate", help="check a run directory against the output contract")
    val_p.add_argument("outdir", type=Path)
    args = parser.parse_args(argv)

    if args.command == "validate":
        problems = outputs.validate(args.outdir)
        for p in problems:
            print(p, file=sys.stderr)
        print("valid" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    started = time.perf_counter()
    try:
        summary = run(args.request, args.out, args.schema)
    except (RequestError, ProtocolError) as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2
    except DataQualityError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    problems = outputs.validate(args.out)
    for p in problems:
        print(f"output problem: {p}", file=sys.stderr)
    print(json.dumps(summary, sort_keys=True))
    print(f"wrote {args.out} in {time.perf_counter() - started:.1f}s", file=sys.stderr)
    return 1 if problems else 0
