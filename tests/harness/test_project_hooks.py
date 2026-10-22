"""Real hooks against real engine output (the fake-hook tests cannot catch contract drift)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import project_hooks
from harness.memory import screen

REQUEST = {"dataset": {"kind": "synthetic", "seed": 3, "symbols": 3, "days": 1008, "regime_mix": "balanced"},
           "strategies": ["trend", "meanrev"], "costs": {"fee_bps": 1.0, "slippage_bps": 5.0},
           "walk_forward": {"train_days": 252, "test_days": 126}, "holdout_fraction": 0.2, "allow_short": False}


def test_memory_candidates_on_real_outputs(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps(REQUEST))
    out = tmp_path / "out"
    subprocess.run([sys.executable, "-m", "quantfoundry", "run", "--request", str(req), "--out", str(out)], check=True)
    assert project_hooks.validate_outputs(out) == []
    state = tmp_path / "state"
    runs = []
    for i in range(3):
        rid = f"quant-foundry-2026102{i}T000000Z-abcdef12-a1"
        shutil.copytree(out, state / "runs" / rid)
        runs.append({"run_id": rid, "status": "completed", "created_at": f"2026-10-2{i}T00:00:00Z"})
    (state / "index.json").write_text(json.dumps({"runs": runs}))
    candidates = project_hooks.memory_candidates(state)
    assert {c["topic"] for c in candidates} >= {"Strategy 'trend' across synthetic regimes",
                                                "Strategy 'meanrev' across synthetic regimes"}
    for c in candidates:
        entry = {**c, "id": "mem-0123456789", "status": "active", "date": "2026-10-21", "supersedes": []}
        assert screen(entry) == [], (c["topic"], screen(entry))


def test_request_problems_matches_engine_feasibility():
    assert project_hooks.request_problems(REQUEST) == []
    bad = json.loads(json.dumps(REQUEST))
    bad["walk_forward"]["train_days"] = 756
    assert project_hooks.request_problems(bad)
