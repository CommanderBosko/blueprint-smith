"""The harness for M2 (docs/m2-plan.md, piece A): stacked belts fed by script, research-all runs with legendary
machines and modules, and the machine bar (blocked on output fails, idle doesn't).

Runs the real Factorio 2.0.77 headless server, so it's skipped when none is installed. Cases run in parallel.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
from draftsman.blueprintable import Blueprint
from draftsman.entity import new_entity

from blueprint_smith import harness
from blueprint_smith.generators import Port
from blueprint_smith.harness import runner

pytestmark = pytest.mark.harness

BELT = "turbo-transport-belt"


def straight_belt(stack: int, rate: float, length: int = 20):
    """A turbo belt flowing south, iron plates in at the top and out at the bottom."""
    bp = Blueprint()
    for y in range(length):
        bp.entities.append(new_entity(BELT, tile_position=(0, y), direction=8))
    ports = [Port("input", "iron-plate", BELT, (0, 0), 8, rate, stack),
             Port("output", "iron-plate", BELT, (0, length - 1), 8, rate, stack)]
    return bp.to_string(), ports, {"warmup_ticks": 600, "window_ticks": 3600}


def legendary_plant():
    """A legendary electromagnetic plant with 5 legendary productivity-3 and one legendary beacon of 2 legendary
    speed-3: crafting speed 2 x 2.5 x (1 - 5 x 0.15 + 2 x 1.25 x 2.5) = 32.5, productivity +50% + 5 x 25%."""
    bp = Blueprint()
    plant = new_entity("electromagnetic-plant", tile_position=(0, 0), recipe="electronic-circuit", quality="legendary")
    plant.request_modules("productivity-module-3", range(5), quality="legendary")
    beacon = new_entity("beacon", tile_position=(4, 0), quality="legendary")
    beacon.request_modules("speed-module-3", range(2), quality="legendary")
    for e in (plant, beacon, new_entity("substation", tile_position=(4, 3), quality="legendary")):
        bp.entities.append(e)
    return bp.to_string(), [], {"warmup_ticks": 60, "window_ticks": 600}


def plant_without_unloading():
    """A plant fed copper plates from a stacked belt by a stack inserter, with nothing taking its cable out."""
    bp = Blueprint()
    bp.entities.append(new_entity("electromagnetic-plant", tile_position=(0, 0), recipe="copper-cable",
                                  quality="legendary"))
    bp.entities.append(new_entity("stack-inserter", tile_position=(4, 1), direction=4, quality="legendary"))
    for y in range(6):
        bp.entities.append(new_entity(BELT, tile_position=(5, y), direction=8))
    bp.entities.append(new_entity("substation", tile_position=(-2, 0)))
    bp.generate_power_connections(only_axis=True)
    ports = [Port("input", "copper-plate", BELT, (7, 0), 8, 240, 4)]  # tiles from the substation's corner
    return bp.to_string(), ports, {"warmup_ticks": 600, "window_ticks": 600}


CASES = {
    "stacked": lambda: straight_belt(4, 240),
    "loader": lambda: straight_belt(1, 60),
    "legendary": legendary_plant,
    "blocked": plant_without_unloading,
}


def need_server():
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")


@pytest.fixture(scope="module")
def runs() -> dict[str, tuple[harness.HarnessResult, harness.Verdict]]:
    need_server()
    jobs = {name: make() for name, make in CASES.items()}

    def go(name):
        s, ports, ticks = jobs[name]
        r = harness.run(s, ports, research="all", **ticks)
        return name, r, harness.judge(r)

    with ThreadPoolExecutor(len(jobs)) as ex:
        return {name: (r, v) for name, r, v in ex.map(go, jobs)}


def test_research_all_unlocks_belt_stacking_and_stack_inserter_capacity(runs):
    r, _ = runs["stacked"]
    assert r.raw["research"] == {"state": "all", "belt_stack_size_bonus": 3, "bulk_inserter_capacity_bonus": 11,
                                 "inserter_stack_size_bonus": 3}


def test_a_stacked_input_fills_a_turbo_belt_at_240(runs):
    """No loader can stack, so the script inserts stacks of 4 on both lanes; the loader sink keeps up."""
    r, v = runs["stacked"]
    assert v.passed, "\n".join(v.problems)
    (o,) = r.outputs
    assert o.rate == pytest.approx(240, rel=0.02)
    assert o.lane_rates == pytest.approx([120, 120], rel=0.02)
    assert o.produced_rate is None  # no machine makes the plates: judged on what reached the sink
    assert r.power.harness_linked is None  # no pole to link, and nothing that needs power


def test_a_stack_1_input_still_feeds_through_a_loader_at_60(runs):
    r, v = runs["loader"]
    assert v.passed, "\n".join(v.problems)
    assert r.outputs[0].rate == pytest.approx(60, rel=0.02)
    assert r.outputs[0].lane_rates == pytest.approx([30, 30], rel=0.02)


def test_legendary_machines_get_their_legendary_modules(runs):
    r, v = runs["legendary"]
    assert r.build == harness.BuildStatus(0, 0, [])
    (m,) = r.machines
    assert (m.name, m.quality, m.recipe) == ("electromagnetic-plant", "legendary", "electronic-circuit")
    assert m.crafting_speed == pytest.approx(32.5)
    assert m.productivity == pytest.approx(1.75)
    # unfed, it waits for ingredients the whole window: reported, not failed
    assert m.statuses == {"item_ingredient_shortage": 600}
    assert v.problems == ["no output was measured, so throughput can't be judged"]
    assert "utilisation legendary electromagnetic-plant (electronic-circuit): working 0.0% at (2, 2)" in v.summary


def test_a_machine_that_cant_unload_fails_as_blocked_on_output(runs):
    r, v = runs["blocked"]
    (m,) = r.machines
    assert m.statuses == {"full_output": 600}
    assert "electromagnetic-plant at (4, 2): blocked on output 100.0% of the window (needs <= 5%), mostly " \
           "full_output" in v.problems


def test_the_mod_rejects_a_stack_outside_1_to_4(monkeypatch):
    """job_lua checks the stack first; the mod checks it again, for a job written some other way."""
    need_server()
    monkeypatch.setattr(runner, "MAX_STACK", 9)
    s, ports, ticks = straight_belt(5, 300)
    r = harness.run(s, ports, **ticks)
    assert r.build.errors == [f"port {i}: stack must be an integer from 1 to 4, got 5" for i in (1, 2)]
    assert not harness.judge(r).passed
