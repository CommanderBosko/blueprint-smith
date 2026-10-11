"""Calibration: the headless harness must agree with what the user saw in-game (docs/techniques.md).

Runs the real Factorio 2.0.77 headless server, so it's skipped when none is installed (`blueprint-smith
install-server`). Every case runs twice, in parallel, to show the verdict is repeatable.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from draftsman.blueprintable import Blueprint
from draftsman.utils import JSON_to_string, string_to_JSON

from blueprint_smith import harness
from blueprint_smith.evaluate import timing
from blueprint_smith.generators import Port
from blueprint_smith.harness.verdict import GROWTH_MAX
from blueprint_smith.pipeline import build

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "harness"
EXAMPLES = ("smelting_column", "smelting_column_copper", "smelting_column_steel", "steel_column")
# The single-sided layout from before lane balancing (T1), frozen from git f1d113a with hand-declared ports.
PRE_T1 = ("pre_t1_copper_24", "pre_t1_copper_48", "pre_t1_steel_24")
RUNS = 2

pytestmark = pytest.mark.harness


def _cases() -> dict[str, tuple[str, list[Port]]]:
    cases = {}
    for name in EXAMPLES:
        with open(ROOT / "examples" / f"{name}.json") as f:
            b = build(json.load(f))
        cases[name] = (b.string, b.ports)
    for name in PRE_T1:
        d = json.loads((FIXTURES / f"{name}.json").read_text())
        ports = [Port(p["role"], p["item"], p["belt"], tuple(p["tile"]), p["direction"], p["rate"]) for p in d["ports"]]
        cases[name] = (d["blueprint"], ports)
    # A pasted blueprint keeps only the wires it carries (F6): strip them to get the first in-game import.
    j = string_to_JSON(cases["smelting_column"][0])
    j["blueprint"].pop("wires", None)
    cases["unwired_iron"] = (JSON_to_string(j), cases["smelting_column"][1])
    return cases


@pytest.fixture(scope="module")
def runs() -> dict[str, list[tuple[harness.HarnessResult, harness.Verdict]]]:
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")
    cases = _cases()  # builds stay serial: pipeline.build records warnings process-wide

    def go(name):
        s, ports = cases[name]
        warmup, window = timing(Blueprint.from_string(s), ports)
        r = harness.run(s, ports, warmup_ticks=warmup, window_ticks=window)
        return name, r, harness.judge(r)

    out: dict[str, list] = {}
    with ThreadPoolExecutor(8) as ex:
        for name, r, v in ex.map(go, [n for n in cases for _ in range(RUNS)]):
            out.setdefault(name, []).append((r, v))
    return out


@pytest.mark.parametrize("name", EXAMPLES)
def test_confirmed_samples_pass_at_their_target(runs, name):
    """Every sample ran as specified in-game (2026-10-11) with every furnace busy."""
    for r, v in runs[name]:
        assert v.passed, "\n".join(v.problems)
        o = r.outputs[0]
        assert o.produced_rate == pytest.approx(o.target, rel=0.01)
        assert o.rate == pytest.approx(o.target, rel=0.02)
        assert min(m.working for m in r.machines) >= 0.99
        assert max(m.output_growth for m in r.machines) <= GROWTH_MAX


@pytest.mark.parametrize("name, lane", [("smelting_column", 7.5), ("smelting_column_copper", 15.0)])
def test_lane_balancing_fills_both_lanes(runs, name, lane):
    """T1: iron 15/s filled both lanes of a yellow belt in-game; copper 30/s does the same on red."""
    for r, _ in runs[name]:
        assert r.outputs[0].lane_rates == pytest.approx([lane, lane], rel=0.02)


def test_pre_t1_copper_puts_every_plate_on_one_lane(runs):
    """F1, confirmed in-game: the old layout put every plate on the far lane. It still made its 15/s, so it passes
    the hard bar; lane fill is reported, not failed."""
    for r, v in runs["pre_t1_copper_24"]:
        assert sorted(r.outputs[0].lane_rates) == pytest.approx([0, 15], abs=0.1)
        assert v.passed


def test_pre_t1_copper_asked_for_a_full_belt_backs_up(runs):
    """Asked for a full red belt, the old layout's one lane carries 15/s and the bottom furnaces back up."""
    for r, v in runs["pre_t1_copper_48"]:
        assert not v.passed
        assert r.outputs[0].rate == pytest.approx(15, rel=0.02)
        assert any("output backing up" in p for p in v.problems)


def test_unwired_poles_fail_with_no_power(runs):
    """F6, confirmed in-game: without wires in the blueprint, the poles don't join and the column is dead."""
    for r, v in runs["unwired_iron"]:
        assert not v.passed
        assert r.power.unpowered_machine_ticks > 0
        assert sum(m.statuses.get("no_power", 0) > 0 for m in r.machines) >= len(r.machines) // 2


@pytest.mark.xfail(strict=True, reason=(
    "unresolved: in-game (output consumed downstream) the old steel column's last furnaces couldn't unload; "
    "with a free-draining sink the harness sees every furnace working, even after a 20-minute warmup. "
    "See the open questions in docs/techniques.md."))
def test_pre_t1_steel_jams_like_in_game(runs):
    for _, v in runs["pre_t1_steel_24"]:
        assert not v.passed


@pytest.mark.parametrize("name", (*EXAMPLES, *PRE_T1, "unwired_iron"))
def test_verdicts_are_repeatable(runs, name):
    (r1, v1), (r2, v2) = runs[name]
    assert v1.passed == v2.passed
    for a, b in zip(r1.outputs, r2.outputs):
        assert b.produced_rate == pytest.approx(a.produced_rate, rel=0.01, abs=0.01)
