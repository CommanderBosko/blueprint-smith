"""circuit_block (M2 piece E): the green circuit block's layout, its spec options and flow check, and harness runs
of the default and an under-sized variant."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from draftsman.constants import Direction

from blueprint_smith import checks, generators, harness
from blueprint_smith.errors import BuildError, SpecError
from blueprint_smith.evaluate import evaluate
from blueprint_smith.generators import circuit_block as cb
from blueprint_smith.harness.verdict import BLOCKED, feeds_only_machines, share
from blueprint_smith.pipeline import build

SPEC = {"type": "circuit_block"}


def _at(e) -> tuple[int, int]:
    return e.tile_position.x, e.tile_position.y


def _inserters(bp) -> set[tuple[int, int]]:
    return {_at(e) for e in bp.entities if e.name == cb.INSERTER}


def test_the_default_block_builds_clean():
    b = build({**SPEC, "rate": 240})
    assert not [n for n in b.notes if n.startswith("WARNING")]
    names = [e.name for e in b.blueprint.entities]
    assert (names.count(cb.PLANT), names.count(cb.BEACON), names.count(cb.INSERTER), names.count(cb.POLE)) == (2, 2, 10, 1)
    assert all(e.quality == "legendary" for e in b.blueprint.entities if e.name in (cb.PLANT, cb.BEACON, cb.INSERTER))


def test_ports_are_stacked_at_the_west_and_south_edges():
    b = build(SPEC)
    copper, iron, out = b.ports
    # the blueprint's top-left is (-7, -5): copper (-7, 1), iron (-7, 5), circuits out (5, 5)
    assert (copper.item, copper.tile, copper.direction, copper.stack) == ("copper-plate", (0, 6), 4, 4)
    assert (iron.item, iron.tile, iron.direction, iron.stack) == ("iron-plate", (0, 10), 4, 4)
    assert (out.role, out.item, out.tile, out.direction, out.stack, out.rate) == (
        "output", "electronic-circuit", (12, 10), 8, 4, 240)
    assert iron.rate == pytest.approx(240 / 2.75)  # 1 iron a craft at +175% productivity
    assert copper.rate == pytest.approx(240 / 2.75 * 3 / 2 / 2.75)  # 3 cable a craft, 2 cable a copper craft


def test_both_beacons_reach_both_plants():
    bp = build(SPEC).blueprint
    targets = checks.beacon_targets(bp)
    assert sorted(e.recipe for e in targets) == ["copper-cable", "electronic-circuit"]
    assert all(len(bs) == 2 for bs in targets.values())


@pytest.mark.parametrize("rate, beacons, iron, cable, per_lane", [
    (240, 2, 2, 3, 2),  # the plan: 87.3 iron/s is just over one inserter's 87.47 x 98%, 262 cable/s needs 3
    (100, 1, 1, 1, 1),  # 1 beacon makes 178.75/s; 50/s a lane fits one inserter's 80
])
def test_defaults_come_from_the_solver_and_the_measured_rates(rate, beacons, iron, cable, per_lane):
    bp = build({**SPEC, "rate": rate}).blueprint
    ins = _inserters(bp)
    assert sum(e.name == cb.BEACON for e in bp.entities) == beacons
    assert sum((x, cb.IRON_INSERTER_ROW) in ins for x in range(4)) == iron
    assert sum((cb.CABLE_X, y) in ins for y in range(4)) == cable
    assert sum((cb.EAST_X, y) in ins for y in range(4)) == per_lane
    assert sum((x, cb.NORTH_Y) in ins for x in range(4)) == per_lane


def test_options_override_the_defaults():
    bp = build({**SPEC, "beacons": 1, "iron_inserters": 4, "cable_inserters": 4, "east_inserters": 3,
                "north_inserters": 1}).blueprint
    ins = _inserters(bp)
    assert sum(e.name == cb.BEACON for e in bp.entities) == 1
    assert {(x, cb.IRON_INSERTER_ROW) for x in range(4)} <= ins
    assert {(cb.CABLE_X, y) for y in range(4)} <= ins
    assert sum((cb.EAST_X, y) in ins for y in range(4)) == 3
    assert sum((x, cb.NORTH_Y) in ins for x in range(4)) == 1


@pytest.mark.parametrize("option, warning", [
    ({"beacons": 1}, "the circuit plant makes 178.75/s, under the 240/s target"),
    ({"iron_inserters": 1}, "iron belt -> circuit plant carries 87.47/s, under 87.27/s with the harness's 98% margin"),
    ({"north_inserters": 1}, "circuit plant -> stub -> west lane carries 80.00/s, under 120.00/s with"),
])
def test_under_sized_parts_are_warned_about(option, warning):
    assert any(warning in n for n in build({**SPEC, **option}).notes)


@pytest.mark.parametrize("bad", [
    {"rate": 0}, {"rate": 241}, {"rate": "240"}, {"rate": True},
    {"quality": "mythic"},
    {"beacons": 3}, {"beacons": -1},
    {"iron_inserters": 0}, {"cable_inserters": 5}, {"east_inserters": 1.5}, {"north_inserters": None},
])
def test_spec_errors(bad):
    with pytest.raises(SpecError):
        build({**SPEC, **bad})


def _mutated(monkeypatch, mutate):
    orig = generators.REGISTRY["circuit_block"]

    def wrapper(spec):
        entities, notes, ports = orig(spec)
        mutate(entities)
        return entities, notes, ports

    monkeypatch.setitem(generators.REGISTRY, "circuit_block", wrapper)


def _drop(pred):
    return lambda es: es.__setitem__(slice(None), [e for e in es if not pred(e)])


def _set(pred, attr, value):
    return lambda es: [setattr(e, attr, value) for e in es if pred(e)]


def _is(name, *tiles):
    return lambda e: e.name == name and _at(e) in tiles


@pytest.mark.parametrize("mutate, message", [
    # an iron inserter turned round: it unloads the circuit plant onto the iron belt
    (_set(_is(cb.INSERTER, (0, 4)), "direction", Direction.NORTH), "moves items from circuit plant to iron belt"),
    # no stub inserters: only the east lane fills
    (_drop(_is(cb.INSERTER, (0, -1), (1, -1))), "no inserter moves items from circuit plant to stub"),
    (_drop(_is(cb.INSERTER, *((-1, y) for y in range(4)))), "no inserter moves items from cable plant to circuit plant"),
    # without the belt above it, the side-load tile becomes a turn and the stub joins the east lane
    (_drop(_is(cb.BELT, (5, -3))), "the output belt above the side-load tile"),
    (_set(_is(cb.BELT, *((x, -2) for x in range(5))), "direction", Direction.WEST), "on the stub must flow east"),
    (_set(_is(cb.BELT, (5, 2)), "direction", Direction.NORTH), "on the output belt must flow south"),
    (_set(_is(cb.PLANT, (-5, 0)), "recipe", "electronic-circuit"), "makes electronic-circuit; the layout has"),
    (_drop(_is(cb.PLANT, (-5, 0))), "no copper-cable plant at (-5, 0)"),
])
def test_broken_layout_is_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, mutate)
    with pytest.raises(BuildError) as ei:
        build(SPEC)
    assert any(message in p for p in ei.value.problems), ei.value.problems


# --- the harness (real server; skipped without one) ---------------------------------------------------------

VARIANTS = {"default": SPEC, "one stub inserter": {**SPEC, "north_inserters": 1}}


@pytest.fixture(scope="module")
def runs():
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")
    built = {name: build(spec) for name, spec in VARIANTS.items()}  # serially: build records warnings process-wide
    with ThreadPoolExecutor(len(built)) as ex:
        return dict(zip(built, ex.map(lambda b: evaluate(b, research="all"), built.values())))


@pytest.mark.harness
def test_the_default_block_fills_a_stacked_turbo_belt(runs):
    ev = runs["default"]
    assert ev.verdict.passed, "\n".join(ev.verdict.problems)
    (o,) = ev.result.outputs
    assert o.produced_rate >= 0.98 * 240
    assert o.lane_rates == pytest.approx([120, 120], rel=0.02)
    cable, circuit = sorted(ev.result.machines, key=lambda m: m.recipe)
    # the cable plant has spare capacity, which direct insertion shows as blocked: reported, not judged
    assert feeds_only_machines(cable) and not feeds_only_machines(circuit)
    assert share(circuit, BLOCKED, ev.window_ticks) <= 0.05


@pytest.mark.harness
def test_one_stub_inserter_fails_on_the_west_lane(runs):
    ev = runs["one stub inserter"]
    assert not ev.verdict.passed
    (o,) = ev.result.outputs
    assert o.lane_rates == pytest.approx([120, 80], rel=0.02)
    assert any(p.startswith("output electronic-circuit:") for p in ev.verdict.problems)
