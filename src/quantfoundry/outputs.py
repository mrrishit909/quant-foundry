"""Output contract: deterministic writers for a run directory and its validator."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
from pathlib import Path

import numpy as np

from quantfoundry import __version__
from quantfoundry.research.metrics import METRIC_KEYS

MAX_TOTAL_BYTES = 2_000_000
EXPERIMENT_COLUMNS = ["strategy", "params", "window", "segment", *METRIC_KEYS]
TRADE_COLUMNS = [
    "date",
    "strategy",
    "symbol",
    "side",
    "qty",
    "ref_open",
    "fill_price",
    "fee",
    "slippage_cost",
    "segment",
    "window",
]
REQUIRED_JSON = {
    "manifest.json": ["params", "dataset", "package_version", "input_manifest_hash"],
    "data_quality.json": ["status", "checks"],
    "strategies.json": ["strategies"],
    "assumptions.json": ["signal_timing", "fill_timing", "fees", "slippage", "missing_data", "calendar"],
    "walkforward.json": ["windows", "strategies"],
    "sensitivity.json": ["strategies"],
    "holdout.json": ["span", "sealed", "selection_frozen_before_holdout", "evaluations"],
    "benchmarks.json": ["buyhold", "cash"],
    "results.json": ["generated_by", "strategies", "benchmarks", "summary"],
    "checks.json": ["accounting", "lookahead_probe", "determinism", "holdout"],
}
REQUIRED_FILES = sorted([*REQUIRED_JSON, "dataset.csv.gz", "experiments.csv", "equity.csv", "trades.csv", "report.md"])


def _num(x: float) -> float | None:
    x = float(x)
    if not math.isfinite(x):
        return None
    return float(f"{x:.10g}") + 0.0  # + 0.0 turns -0.0 into 0.0


def clean(obj):
    """JSON-ready copy: numpy scalars converted, floats rounded to 10 significant digits."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _num(obj)
    return obj


def dumps(obj) -> str:
    return json.dumps(clean(obj), sort_keys=True, indent=2, allow_nan=False) + "\n"


def compact(obj) -> str:
    return json.dumps(clean(obj), sort_keys=True, separators=(",", ":"))


def _cell(x) -> str:
    if isinstance(x, (bool, np.bool_)):
        return str(bool(x)).lower()
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return f"{_num(x):.10g}"
    if isinstance(x, dict):
        return compact(x)
    return str(x)


def _csv(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def write_run(
    outdir: Path,
    *,
    manifest: dict,
    dataset_csv: bytes,
    quality: dict,
    strategies: list[dict],
    assumptions: dict,
    research: dict,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    def text(name: str, content: str) -> None:
        (outdir / name).write_text(content, encoding="utf-8")

    text("manifest.json", dumps(manifest))
    (outdir / "dataset.csv.gz").write_bytes(gzip.compress(dataset_csv, compresslevel=9, mtime=0))
    text("data_quality.json", dumps(quality))
    text("strategies.json", dumps({"strategies": strategies}))
    text("assumptions.json", dumps(assumptions))
    text(
        "walkforward.json",
        dumps({"windows": research["windows"], "strategies": research["walkforward"]}),
    )
    text(
        "experiments.csv",
        _csv(EXPERIMENT_COLUMNS, [[_cell(e[c]) for c in EXPERIMENT_COLUMNS] for e in research["experiments"]]),
    )
    text("sensitivity.json", dumps({"strategies": research["sensitivity"]}))
    text("holdout.json", dumps(research["holdout"]))
    text("benchmarks.json", dumps(research["benchmarks"]))

    eq = research["equity"]
    names = list(eq["columns"])
    text(
        "equity.csv",
        _csv(
            ["date", "segment", *names],
            [
                [d, s, *(f"{eq['columns'][k][i]:.2f}" for k in names)]
                for i, (d, s) in enumerate(zip(eq["dates"], eq["segments"], strict=True))
            ],
        ),
    )
    money = {"ref_open", "fill_price", "fee", "slippage_cost"}
    text(
        "trades.csv",
        _csv(
            TRADE_COLUMNS,
            [[f"{t[c]:.4f}" if c in money else _cell(t[c]) for c in TRADE_COLUMNS] for t in research["trades"]],
        ),
    )
    results = {
        "generated_by": f"quantfoundry {__version__}",
        "strategies": research["results"],
        "benchmarks": {
            k: {seg: v[seg]["metrics"] for seg in ("oos", "holdout")} for k, v in research["benchmarks"].items()
        },
        "summary": research["summary"],
    }
    text("results.json", dumps(results))
    text("checks.json", dumps(research["checks"]))
    text("report.md", render_report(manifest, quality, assumptions, research))


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def render_report(manifest: dict, quality: dict, assumptions: dict, research: dict) -> str:
    ds = manifest["dataset"]
    p = manifest["params"]
    wf = p["walk_forward"]
    bh = research["benchmarks"]["buyhold"]
    checks = research["checks"]
    lines = [
        "# Quant Foundry research report",
        "",
        "Historical backtest on SYNTHETIC data. No brokerage, no live orders, no profit claims.",
        "",
        "## Summary",
        "",
        research["summary"]["headline"],
        "",
        "## Dataset",
        "",
        f"- Synthetic, seed {ds['seed']}, {ds['symbols']} symbols, {ds['days']} days, regime mix `{ds['regime_mix']}`",
        f"- Span {ds['start']} to {ds['end']}, {ds['rows']} rows, sha256 `{ds['sha256']}`",
        f"- Calendar: {ds['calendar']}",
        f"- Injected defects: {len(ds['injected_defects'])} missing bar(s): "
        + ", ".join(f"{d['symbol']} {d['date']}" for d in ds["injected_defects"]),
        f"- Data quality status: {quality['status']} ("
        + ", ".join(f"{c['name']}={c['status']}" for c in quality["checks"])
        + ")",
        f"- Input manifest hash: `{manifest['input_manifest_hash']}`",
        "",
        "## Protocol",
        "",
        f"- Sealed holdout: {research['holdout']['span'][0]} to {research['holdout']['span'][1]} "
        f"(last {_pct(p['holdout_fraction'])} of dates, rounded down)",
        f"- Rolling walk-forward on the development period: {len(research['windows'])} windows of "
        f"{wf['train_days']} train / {wf['test_days']} test days, step {wf['test_days']}, after a "
        f"{assumptions['warmup']['prefix_bars']}-bar warm-up prefix",
        "- Selection: best in-sample Sharpe over the full grid (ties: fewer trades, then lexicographic params)",
        "- Final params frozen from the last window, then the holdout is evaluated once per strategy",
        f"- Costs: fee {research['costs']['fee_bps']} bps, slippage {research['costs']['slippage_bps']} bps",
        "- Acceptance needs all of: OOS Sharpe > 0.30, OOS Sharpe > buy-and-hold OOS Sharpe, holdout "
        "return > 0, parameter stability >= 0.30, at least 10 OOS trades",
        "",
        "## Assumptions",
        "",
        *[f"- **{name}**: {item['text']}" for name, item in sorted(assumptions.items())],
        "",
        "## Results",
        "",
        "| Strategy | Verdict | OOS Sharpe | OOS return | OOS max DD | OOS trades | Holdout return | "
        "Stability | Frozen params |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in research["results"]:
        o, hm = r["oos_metrics"], r["holdout_metrics"]
        lines.append(
            f"| {r['id']} | {r['verdict']} | {o['sharpe']:.2f} | {_pct(o['total_return'])} | "
            f"{_pct(o['max_drawdown'])} | {o['trades']} | {_pct(hm['total_return'])} | "
            f"{r['stability']:.2f} | `{compact(r['frozen_params'])}` |"
        )
    for name, label in (("buyhold", "buy-and-hold"), ("cash", "cash")):
        b = research["benchmarks"][name]
        lines.append(
            f"| {label} (benchmark) | n/a | {b['oos']['metrics']['sharpe']:.2f} | "
            f"{_pct(b['oos']['metrics']['total_return'])} | {_pct(b['oos']['metrics']['max_drawdown'])} | "
            f"{b['oos']['metrics']['trades']} | {_pct(b['holdout']['metrics']['total_return'])} | n/a | n/a |"
        )
    lines += ["", f"OOS span {bh['oos']['span'][0]} to {bh['oos']['span'][1]}.", "", "## Rejections", ""]
    rejected = [r for r in research["results"] if r["verdict"] == "rejected"]
    if not rejected:
        lines.append("No strategy was rejected.")
    for r in rejected:
        lines.append(f"- **{r['id']}**")
        lines += [f"  - {reason}" for reason in r["reasons"]]
    lines += [
        "",
        "## Self checks",
        "",
        f"- Accounting: max reconciliation error {checks['accounting']['max_abs_error']:.3g} over "
        f"{checks['accounting']['backtests_checked']} backtests (tolerance 1e-6): "
        + ("passed" if checks["accounting"]["passed"] else "FAILED"),
        f"- Lookahead probe at cutoff {checks['lookahead_probe']['cutoff_date']}: "
        + ("passed" if checks["lookahead_probe"]["passed"] else "FAILED"),
        "- Holdout evaluated exactly once per strategy: " + ("yes" if checks["holdout"]["evaluated_once"] else "NO"),
        f"- Missing-bar events in recorded backtests: {len(checks['missing_data_events'])}",
        "",
        "## Limitations",
        "",
        "- Synthetic data only: regimes, jumps and defects are generated, so no result transfers to real markets.",
        "- No exchange holidays, no corporate actions (splits, dividends), no delistings or survivorship effects.",
        "- Long-only, no leverage, cash earns nothing.",
        "- Signals at the close fill at the next open; no intraday execution, no partial fills.",
        "- Market impact is a fixed slippage in bps; no spread or volume-dependent impact model.",
        "- A small parameter grid and few walk-forward windows; a high Sharpe here can still be luck.",
        "",
    ]
    return "\n".join(lines)


def validate(outdir: str | Path) -> list[str]:
    """Problems with a run directory (empty list when it satisfies the output contract)."""
    outdir = Path(outdir)
    problems = [f"missing file {name}" for name in REQUIRED_FILES if not (outdir / name).is_file()]
    if problems:
        return problems
    data: dict[str, dict] = {}
    for name, keys in REQUIRED_JSON.items():
        try:
            data[name] = json.loads((outdir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name} does not parse: {exc}")
            continue
        problems += [f"{name} lacks key {k!r}" for k in keys if k not in data[name]]
    if problems:
        return problems

    def rows(name: str) -> list[list[str]]:
        with open(outdir / name, newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))

    results = data["results.json"]
    ids = [s.get("id") for s in results["strategies"]]
    requested = data["manifest.json"]["params"].get("strategies")
    if ids != requested:
        problems.append(f"results.json lists strategies {ids}, the request asked for {requested}")
    for name, header in (("experiments.csv", EXPERIMENT_COLUMNS), ("trades.csv", TRADE_COLUMNS)):
        got = rows(name)
        if not got or got[0] != header:
            problems.append(f"{name} header is {got[0] if got else None}, expected {header}")
    equity = rows("equity.csv")
    if not equity or equity[0] != ["date", "segment", *ids, "buyhold", "cash"]:
        problems.append(f"equity.csv header {equity[0] if equity else None} does not match the strategies")
    else:
        for row in equity[1:]:
            try:
                values = [float(v) for v in row[2:]]
            except ValueError:
                problems.append(f"equity.csv has a non-numeric value on {row[0]}")
                break
            if len(values) != len(ids) + 2 or not all(math.isfinite(v) for v in values):
                problems.append(f"equity.csv has a missing or non-finite value on {row[0]}")
                break
    summary = results["summary"]
    if summary.get("accepted", -1) + summary.get("rejected", -1) != len(ids):
        problems.append("summary accepted + rejected does not equal the number of strategies")
    for s in results["strategies"]:
        if s.get("verdict") not in ("accepted", "rejected"):
            problems.append(f"strategy {s.get('id')} has verdict {s.get('verdict')!r}")
        if s.get("verdict") == "rejected" and not s.get("reasons"):
            problems.append(f"strategy {s.get('id')} is rejected without reasons")
    checks = data["checks.json"]
    if not checks["accounting"].get("passed"):
        problems.append(f"accounting check failed: max_abs_error {checks['accounting'].get('max_abs_error')}")
    if not checks["lookahead_probe"].get("passed"):
        problems.append("lookahead probe failed")
    if not checks["holdout"].get("evaluated_once"):
        problems.append("holdout was not evaluated exactly once per strategy")
    total = sum(f.stat().st_size for f in outdir.rglob("*") if f.is_file())
    if total >= MAX_TOTAL_BYTES:
        problems.append(f"run directory is {total} bytes; the limit is {MAX_TOTAL_BYTES}")
    return problems
