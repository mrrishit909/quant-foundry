import pytest
from qf_helpers import SMALL_REQUEST, run_cli, synthetic_panel


@pytest.fixture(scope="session")
def small_run(tmp_path_factory):
    """One CLI run of SMALL_REQUEST (fee 10 bps, slippage 25 bps), shared read-only by many tests."""
    return run_cli(SMALL_REQUEST, tmp_path_factory.mktemp("small"), "run")


@pytest.fixture(scope="session")
def small_panel():
    return synthetic_panel()
