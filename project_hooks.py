"""Quant Foundry hooks for the generic harness (validation, headline, holdout audit, memory)."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from harness.core import config, pretty
from harness.state import read_json, write_immutable

PUBLIC_FILES = [
    "manifest.json", "data_quality.json", "strategies.json", "assumptions.json", "walkforward.json",
    "experiments.csv", "sensitivity.json", "holdout.json", "benchmarks.json", "equity.csv", "trades.csv",
    "results.json", "checks.json", "report.md", "holdout_audit.json",
]


def request_problems(params: dict[str, Any]) -> list[str]:
    """Feasibility beyond the schema: one walk-forward window must fit in the development period."""
    import math

    from quantfoundry.research.protocol import WARMUP_PREFIX

    days = params["dataset"]["days"]
    dev = days - math.floor(days * params["holdout_fraction"])
    wf = params["walk_forward"]
    need = WARMUP_PREFIX + wf["train_days"] + wf["test_days"]
    if dev < need:
        return [f"walk_forward: the development period has {dev} days but one window needs {need} "
                f"({WARMUP_PREFIX} warm-up + {wf['train_days']} train + {wf['test_days']} test); choose more "
                "trading days, shorter windows or a smaller holdout fraction"]
    return []


def validate_outputs(out_dir: Path) -> list[str]:
    from quantfoundry.outputs import validate

    return validate(out_dir)


def headline(out_dir: Path) -> str | None:
    results = json.loads((out_dir / "results.json").read_text())
    return results["summary"]["headline"][:200]


def on_publish(root: Path, record: dict[str, Any], out_dir: Path) -> list[str]:
    """Cross-run holdout audit: a sealed holdout may be evaluated once per dataset and strategy.

    If an earlier run already evaluated the same dataset's holdout for a strategy with different
    frozen parameters, the holdout has been used to compare tuning choices; this run's holdout
    numbers are flagged as contaminated (shown on the site, never silently accepted).
    """
    manifest = json.loads((out_dir / "manifest.json").read_text())
    holdout = json.loads((out_dir / "holdout.json").read_text())
    dataset_sha = manifest["dataset"]["sha256"]
    ledger = read_json(root, "holdout/ledger.json", {"datasets": {}})
    prior = ledger["datasets"].get(dataset_sha, [])
    findings = []
    for ev in holdout["evaluations"]:
        earlier = [p for p in prior if p["strategy"] == ev["strategy"] and p["run_id"] != record["run_id"]]
        changed = [p for p in earlier if p["frozen_params"] != ev["frozen_params"]]
        findings.append({"strategy": ev["strategy"], "prior_evaluations": len(earlier),
                         "contaminated": bool(changed), "prior_runs": [p["run_id"] for p in changed]})
        prior.append({"run_id": record["run_id"], "strategy": ev["strategy"], "frozen_params": ev["frozen_params"]})
    ledger["datasets"][dataset_sha] = prior
    (root / "holdout").mkdir(exist_ok=True)
    (root / "holdout" / "ledger.json").write_text(pretty(ledger))
    rel = f"runs/{record['run_id']}/holdout_audit.json"
    write_immutable(root, rel, pretty({"dataset_sha256": dataset_sha, "strategies": findings}).encode())
    return [rel]


def memory_candidates(root: Path) -> list[dict[str, Any]]:
    """Deterministic lessons: only patterns backed by at least three completed runs."""
    cfg = config()
    index = read_json(root, "index.json", {"runs": []})
    per_strategy: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    warnings: Counter[str] = Counter()
    warn_runs: dict[str, list[str]] = {}
    for entry in index["runs"]:
        if entry["status"] != "completed":
            continue
        results = read_json(root, f"runs/{entry['run_id']}/results.json")
        quality = read_json(root, f"runs/{entry['run_id']}/data_quality.json")
        if not results:
            continue
        for strat in results["strategies"]:
            per_strategy.setdefault(strat["id"], []).append((entry["run_id"], strat))
        for check in (quality or {}).get("checks", []):
            if check.get("status") == "warn":
                name = check.get("name") or check.get("id") or "unnamed"
                warnings[name] += 1
                warn_runs.setdefault(name, []).append(entry["run_id"])
    base = f"https://github.com/{cfg['owner']}/{cfg['repo']}/blob/{cfg['state_branch']}"
    today = date.today()
    out = []
    for strat_id, rows in sorted(per_strategy.items()):
        if len(rows) < 3:
            continue
        rejected = [s for _, s in rows if s["verdict"] == "rejected"]
        reasons = Counter(r.split(" ")[0] + " " + r.split(" ")[1] for s in rejected for r in s["reasons"][:1])
        sharpe = statistics.median(s["oos_metrics"]["sharpe"] for _, s in rows)
        top = reasons.most_common(1)[0][0] if reasons else "n/a"
        run_ids = [rid for rid, _ in rows][:20]
        out.append({
            "topic": f"Strategy '{strat_id}' across synthetic regimes",
            "finding": (f"Rejected in {len(rejected)} of {len(rows)} completed runs; median out-of-sample "
                        f"Sharpe {sharpe:.2f}; most common first rejection reason starts with '{top}'."),
            "supporting_run_ids": run_ids,
            "evidence_links": [f"{base}/runs/{rid}/results.json" for rid in run_ids[:5]],
            "scope": "research-finding",
            "confidence": "high" if len(rows) >= 12 else "medium" if len(rows) >= 6 else "low",
            "revalidate_when": "after 10 more completed runs or any change to the strategy or simulator code",
            "expires_on": (today + timedelta(days=90)).isoformat(),
        })
    for check_id, count in sorted(warnings.items()):
        if count >= 3:
            run_ids = warn_runs[check_id][:20]
            out.append({
                "topic": f"Recurring data-quality warning '{check_id}'",
                "finding": f"The validation check '{check_id}' warned in {count} completed runs.",
                "supporting_run_ids": run_ids,
                "evidence_links": [f"{base}/runs/{rid}/data_quality.json" for rid in run_ids[:5]],
                "scope": "data-quality",
                "confidence": "medium" if count >= 6 else "low",
                "revalidate_when": "after a change to the synthetic generator or validation rules",
                "expires_on": (today + timedelta(days=90)).isoformat(),
            })
    return out
