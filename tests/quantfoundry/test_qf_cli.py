"""CLI request handling, output validation and one end-to-end run at the default size."""

import json
import shutil
import subprocess
import sys
import time

import pytest
from qf_helpers import DEFAULT_REQUEST, SMALL_REQUEST, load, request

from quantfoundry.cli import RequestError, check_request, main
from quantfoundry.outputs import validate


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"allow_short": True}, "long-only"),
        ({"dataset.symbols": 11}, "symbols"),
        ({"strategies": ["trend", "momentum"]}, "momentum"),
        ({"dataset.days": 100}, "days"),
        ({"holdout_fraction": 0.5}, "holdout_fraction"),
        ({"dataset.kind": "csv"}, "kind"),
    ],
)
def test_cli_rejects_invalid_requests(tmp_path, capsys, changes, message):
    req = tmp_path / "req.json"
    req.write_text(json.dumps(request(**changes)))
    out = tmp_path / "out"
    assert main(["run", "--request", str(req), "--out", str(out)]) == 2
    assert message in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"allow_short": True},
        {"dataset.symbols": 11},
        {"dataset.symbols": 3.5},
        {"strategies": ["trend", "momentum"]},
        {"strategies": ["trend", "trend"]},
        {"walk_forward.test_days": 10},
        {"costs.fee_bps": -1},
    ],
)
def test_code_level_bounds_without_schema(changes):
    with pytest.raises(RequestError):
        check_request(request(**changes))
    check_request(request())  # the base request is valid


def test_cli_rejects_nonempty_outdir_and_bad_json(tmp_path, capsys):
    req = tmp_path / "req.json"
    req.write_text(json.dumps(SMALL_REQUEST))
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    assert main(["run", "--request", str(req), "--out", str(out)]) == 2
    assert "must be empty" in capsys.readouterr().err
    req.write_text("{not json")
    assert main(["run", "--request", str(req), "--out", str(tmp_path / "o2")]) == 2


def test_cli_rejects_too_short_development_period(tmp_path, capsys):
    req = tmp_path / "req.json"
    req.write_text(json.dumps(request(**{"walk_forward.train_days": 756, "holdout_fraction": 0.3})))
    assert main(["run", "--request", str(req), "--out", str(tmp_path / "out")]) == 2
    assert "walk-forward window needs" in capsys.readouterr().err


def test_validate_command_flags_problems(small_run, tmp_path):
    assert validate(small_run) == []
    assert main(["validate", str(small_run)]) == 0

    broken = tmp_path / "broken"
    shutil.copytree(small_run, broken)
    (broken / "report.md").unlink()
    assert validate(broken) == ["missing file report.md"]
    assert main(["validate", str(broken)]) == 1

    shutil.copyfile(small_run / "report.md", broken / "report.md")
    lines = (broken / "equity.csv").read_text().splitlines()
    cells = lines[5].split(",")
    cells[3] = "nan"
    lines[5] = ",".join(cells)
    (broken / "equity.csv").write_text("\n".join(lines) + "\n")
    results = load(broken / "results.json")
    results["summary"]["accepted"] += 1
    (broken / "results.json").write_text(json.dumps(results))
    problems = validate(broken)
    assert any("equity.csv" in p for p in problems)
    assert any("accepted + rejected" in p for p in problems)


def test_end_to_end_default_request(tmp_path):
    req = tmp_path / "request.json"
    req.write_text(json.dumps(DEFAULT_REQUEST))
    out = tmp_path / "run"
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "quantfoundry", "run", "--request", str(req), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.perf_counter() - started
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 60
    summary = json.loads(proc.stdout)
    assert summary["accepted"] + summary["rejected"] == 3
    assert validate(out) == []
    manifest = load(out / "manifest.json")
    assert manifest["input_manifest_hash"].startswith("sha256:") and len(manifest["input_manifest_hash"]) == 71
    assert 1 <= len(manifest["dataset"]["injected_defects"]) <= 3
    assert sum(f.stat().st_size for f in out.iterdir()) < 2_000_000
    quality = load(out / "data_quality.json")
    assert next(c for c in quality["checks"] if c["name"] == "missing_bars")["status"] == "warn"
