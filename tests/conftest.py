"""With $BPS_REQUIRE_HARNESS set (CI sets it), a skipped test fails instead. The harness tests skip when the
headless server or the game's Lua data is missing, and CI mustn't pass without having run them."""
import os

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport():
    report = (yield).get_result()
    if report.skipped and not hasattr(report, "wasxfail") and os.environ.get("BPS_REQUIRE_HARNESS"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"skipped, but $BPS_REQUIRE_HARNESS is set: {reason.removeprefix('Skipped: ')}"
