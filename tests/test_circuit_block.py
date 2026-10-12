"""circuit_block (M2 pieces E and F): the green circuit block's two layouts (copper from the west or the north), its
spec options and flow check, the optimiser's variants and the sizing they share with the notes, and harness runs of
both defaults and an under-sized variant."""
import math
from concurrent.futures import ThreadPoolExecutor

import pytest
from draftsman.constants import Direction
from draftsman.entity import new_entity

from blueprint_smith import checks, generators, harness
from blueprint_smith.errors import BuildError, SpecError
from blueprint_smith.evaluate import evaluate
from blueprint_smith.generators import circuit_block as cb
from blueprint_smith.harness.verdict import BLOCKED, feeds_only_machines, share
from blueprint_smith.pipeline import build

SPEC = {"type": "circuit_block"}
NORTH = {**SPEC, "copper": "north"}


def _at(e) -> tuple[int, int]:
    return e.tile_position.x, e.tile_position.y


def _inserters(bp) -> set[tuple[int, int]]:
    return {_at(e) for e in bp.entities if e.name == cb.INSERTER}


def _footprint(bp) -> tuple[int, int]:
    box = bp.get_world_bounding_box()
    (x1, y1), (x2, y2) = box.top_left, box.bot_right
    return math.ceil(x2) - math.floor(x1), math.ceil(y2) - math.floor(y1)


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


def test_the_north_block_builds_clean():
    b = build(NORTH)
    assert not [n for n in b.notes if n.startswith("WARNING")]
    names = [e.name for e in b.blueprint.entities]
    assert (names.count(cb.PLANT), names.count(cb.BEACON), names.count(cb.INSERTER), names.count(cb.POLE)) == (2, 2, 10, 1)
    (copper,) = [e for e in b.blueprint.entities if e.name == cb.INSERTER and _at(e) == (-5, -1)]
    assert copper.direction == Direction.NORTH  # picks up from the copper belt above it (F7)


def test_north_ports_are_stacked_at_the_west_and_south_edges():
    b = build(NORTH)
    copper, iron, out = b.ports
    # the blueprint's top-left is (-5, -5): copper (-5, -2), iron (-5, 5), circuits out (5, 5)
    assert (copper.item, copper.tile, copper.direction, copper.stack) == ("copper-plate", (0, 3), 4, 4)
    assert (iron.item, iron.tile, iron.direction, iron.stack) == ("iron-plate", (0, 10), 4, 4)
    assert (out.role, out.item, out.tile, out.direction, out.stack, out.rate) == (
        "output", "electronic-circuit", (10, 10), 8, 4, 240)
    assert [p.rate for p in b.ports] == [p.rate for p in build(SPEC).ports]


@pytest.mark.parametrize("copper, size", [("west", (13, 11)), ("north", (11, 11))])
def test_footprint(copper, size):
    assert _footprint(build({**SPEC, "copper": copper}).blueprint) == size


def test_north_moves_only_the_copper_feed_and_the_iron_belt_start():
    def layout(spec):
        return {(e.name, _at(e), int(getattr(e, "direction", 0))) for e in build(spec).blueprint.entities}

    west, north = layout(SPEC), layout(NORTH)
    E, N, W = int(Direction.EAST), int(Direction.NORTH), int(Direction.WEST)
    assert west - north == {(cb.BELT, (-7, 1), E), (cb.INSERTER, (-6, 1), W), (cb.BELT, (-7, 5), E), (cb.BELT, (-6, 5), E)}
    assert north - west == {(cb.BELT, (-5, -2), E), (cb.INSERTER, (-5, -1), N)}


def test_both_beacons_reach_both_plants():
    bp = build(SPEC).blueprint
    targets = checks.beacon_targets(bp)
    assert sorted(e.recipe for e in targets) == ["copper-cable", "electronic-circuit"]
    assert all(len(bs) == 2 for bs in targets.values())


DEFAULTS = [
    (240, 2, 2, 3, 2),  # the plan: 87.3 iron/s is just over one inserter's 87.47 x 98%, 262 cable/s needs 3
    (100, 1, 1, 1, 1),  # 1 beacon makes 178.75/s; 50/s a lane fits one inserter's 80
]


@pytest.mark.parametrize("rate, beacons, iron, cable, per_lane", DEFAULTS)
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


@pytest.mark.parametrize("copper", cb.COPPER_SIDES)
@pytest.mark.parametrize("n, stub", [(1, [3, 4]), (2, [2, 3, 4]), (4, [0, 1, 2, 3, 4])])
def test_stub_starts_under_its_first_inserter(copper, n, stub):
    # T5, the user's in-game tweak (2026-10-12): the stub inserters sit by the output belt, so no stub belt idles
    bp = build({**SPEC, "copper": copper, "north_inserters": n}).blueprint
    ins = _inserters(bp)
    assert sorted(x for x in range(4) if (x, cb.NORTH_Y) in ins) == list(range(4 - n, 4))
    assert sorted(_at(e)[0] for e in bp.entities if e.name == cb.BELT and _at(e)[1] == cb.STUB_Y
                  and _at(e)[0] < cb.OUT_X and _at(e) not in cb.COPPER_BELTS.values()) == stub


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
    {"copper": "south"}, {"copper": "West"}, {"copper": None}, {"copper": ["north"]},
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


def _move(pred, tile, direction=None):
    def mutate(es):
        for e in es:
            if pred(e):
                e.tile_position = tile
                if direction is not None:
                    e.direction = direction
    return mutate


def _add(name, tile, direction):
    return lambda es: es.append(new_entity(name, tile_position=tile, direction=direction))


@pytest.mark.parametrize("mutate, message", [
    # an iron inserter turned round: it unloads the circuit plant onto the iron belt
    (_set(_is(cb.INSERTER, (0, 4)), "direction", Direction.NORTH), "moves items from circuit plant to iron belt"),
    # no stub inserters: only the east lane fills
    (_drop(_is(cb.INSERTER, (2, -1), (3, -1))), "no inserter moves items from circuit plant to stub"),
    # the stub run back to x=0, west of its inserters: belt that carries nothing (T5, the user's tweak 2026-10-12)
    (lambda es: [_add(cb.BELT, (x, -2), Direction.EAST)(es) for x in (0, 1)], "west of its first inserter"),
    # a stub tile missing between the inserters and the output belt
    (_drop(_is(cb.BELT, (3, -2))), "the stub has no belt at x=3"),
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


@pytest.mark.parametrize("mutate, message", [
    # the copper inserter turned round: it unloads the cable plant onto the copper belt
    (_set(_is(cb.INSERTER, (-5, -1)), "direction", Direction.SOUTH), "moves items from cable plant to copper belt"),
    # the copper belt a tile west of where the inserter picks up
    (_move(_is(cb.BELT, (-5, -2)), (-6, -2)), "turbo-transport-belt at (-5.5, -1.5) isn't on one of the layout's belts"),
    (_move(_is(cb.BELT, (-5, -2)), (-6, -2)), "no copper belt: the layout has exactly one"),
    (_add(cb.BELT, (-7, 1), Direction.EAST), "copper belts at (-7, 1), (-5, -2): the layout has exactly one"),
    (_drop(_is(cb.BELT, (-5, -2))), "no inserter moves items from copper belt to cable plant"),
    # the copper inserter moved above the belt: it picks up copper and drops it onto nothing
    (_move(_is(cb.INSERTER, (-5, -1)), (-5, -3), Direction.SOUTH), "moves items from copper belt to nothing"),
    (_set(_is(cb.BELT, (-5, -2)), "direction", Direction.SOUTH), "on the copper belt must flow east"),
])
def test_broken_north_layout_is_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, mutate)
    with pytest.raises(BuildError) as ei:
        build(NORTH)
    assert any(message in p for p in ei.value.problems), ei.value.problems


# --- the optimiser's variants and the sizing they share with the notes ---------------------------------------

REQUEST = {"item": "electronic-circuit", "rate": 240}
KEYS = ["type", "rate", "copper", "beacons", "iron_inserters", "cable_inserters", "east_inserters", "north_inserters"]


def test_circuit_block_registers_its_variants_and_research():
    assert generators.VARIANTS["circuit_block"] is cb.variants
    assert generators.RESEARCH["circuit_block"] == "all"


def test_variants_at_240_legendary():
    specs = cb.variants(REQUEST)
    assert len(specs) == 144  # 2 copper sides x 2 beacons x 4 iron x 2 cable x 3 east x 3 north
    assert all(list(s) == KEYS for s in specs)
    assert len({tuple(s.values()) for s in specs}) == 144

    def values(key):
        return sorted({s[key] for s in specs})

    assert values("copper") == ["north", "west"]
    assert values("beacons") == [2]
    assert values("iron_inserters") == [1, 2, 3, 4]  # one carries 87.47/s against 87.27/s
    assert values("cable_inserters") == [3, 4]
    assert values("east_inserters") == values("north_inserters") == [2, 3, 4]


def test_every_variant_builds():
    failed = {}
    for spec in cb.variants(REQUEST):
        try:
            build(spec)
        except BuildError as e:
            failed[str(spec)] = e.problems
    assert not failed, failed


@pytest.mark.parametrize("request_", [
    {"item": "iron-plate", "rate": 15}, {"rate": 240},
    {**REQUEST, "rate": 240.5}, {**REQUEST, "rate": 0}, {**REQUEST, "rate": -1}, {**REQUEST, "rate": True},
    {**REQUEST, "rate": "240"}, {"item": "electronic-circuit"},
])
def test_no_variants_for_another_item_or_rate(request_):
    assert list(cb.variants(request_)) == []


def test_variants_pass_quality_through():
    specs = cb.variants({**REQUEST, "quality": "legendary"})
    assert len(specs) == 144 and all(s["quality"] == "legendary" for s in specs)
    assert all("quality" not in s for s in cb.variants(REQUEST))
    with pytest.raises(SpecError):
        cb.variants({**REQUEST, "quality": "mythic"})


@pytest.mark.parametrize("counts, bound", [
    ((1, 4, 4, 4, 4), 178.75),  # 1 beacon: the circuit plant makes 178.75/s
    ((2, 4, 2, 4, 4), 220.0),  # 2 cable inserters carry 240/s of the 261.82/s needed: 240 x 240 / 261.82
    ((2, 4, 4, 1, 4), 200.0),  # 1 east inserter: 80 + 120 on the two lanes
    ((2, 1, 4, 4, 4), 240.0),  # 1 iron inserter carries 87.47/s for 87.27/s, so the lanes are the limit
    ((2, 2, 3, 2, 2), 240.0),  # the default
])
def test_the_bound_is_the_tightest_link(counts, bound):
    assert cb.sizing(240, "legendary", *counts).bound == pytest.approx(bound, rel=1e-4)


def test_the_bound_rules_out_one_beacon_and_two_cable_inserters():
    assert cb.sizing(240, "legendary", 1, 4, 4, 4, 4).bound < 0.98 * 240
    assert cb.sizing(240, "legendary", 2, 4, 2, 4, 4).bound < 0.98 * 240
    assert not [s for s in cb.variants(REQUEST) if s["beacons"] == 1 or s["cable_inserters"] == 2]


@pytest.mark.parametrize("rate, beacons, iron, cable, per_lane", DEFAULTS)
def test_the_notes_and_ports_come_from_sizing(rate, beacons, iron, cable, per_lane):
    # no drift: the default build's link notes and port rates are the helper's, and the default is a variant
    b = build({**SPEC, "rate": rate})
    s = cb.sizing(rate, "legendary", beacons, iron, cable, per_lane, per_lane)
    for link in s.links:
        assert (f"{link.name}: {link.inserters} stack inserter(s) carry {link.carries:.2f}/s for {link.demand:.2f}/s"
                in b.notes)
    copper, iron_port, _ = b.ports
    assert (copper.rate, iron_port.rate) == (s.copper, s.iron)
    default = {"type": "circuit_block", "rate": rate, "copper": "west", "beacons": beacons, "iron_inserters": iron,
               "cable_inserters": cable, "east_inserters": per_lane, "north_inserters": per_lane}
    assert default in cb.variants({**REQUEST, "rate": rate})


# --- the harness (real server; skipped without one) ---------------------------------------------------------

HARNESS_SPECS = {"default": SPEC, "north": NORTH, "one stub inserter": {**SPEC, "north_inserters": 1}}


@pytest.fixture(scope="module")
def runs():
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")
    built = {name: build(spec) for name, spec in HARNESS_SPECS.items()}  # serially: build records warnings process-wide
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
def test_the_north_block_fills_a_stacked_turbo_belt(runs):
    ev = runs["north"]
    assert ev.verdict.passed, "\n".join(ev.verdict.problems)
    (o,) = ev.result.outputs
    assert o.produced_rate >= 0.98 * 240
    assert o.lane_rates == pytest.approx([120, 120], rel=0.02)
    cable, circuit = sorted(ev.result.machines, key=lambda m: m.recipe)
    assert feeds_only_machines(cable) and not feeds_only_machines(circuit)
    assert share(circuit, BLOCKED, ev.window_ticks) <= 0.05


@pytest.mark.harness
def test_one_stub_inserter_fails_on_the_west_lane(runs):
    ev = runs["one stub inserter"]
    assert not ev.verdict.passed
    (o,) = ev.result.outputs
    assert o.lane_rates == pytest.approx([120, 80], rel=0.02)
    assert any(p.startswith("output electronic-circuit:") for p in ev.verdict.problems)
