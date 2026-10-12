"""M2 piece B: the primitives the green-circuit block is sized from, measured in micro-blueprints on the headless
2.0.77 server (docs/m2-plan.md; F28 in docs/techniques.md). M2b piece A adds the red-circuit block's: the long-handed
inserter (F29) and a stack inserter taking from a mixed belt (F30) (docs/red-circuits-plan.md). Probes script-feed
or drain the machines around the link under test, so that link is the only bottleneck. Every case runs twice, to
show the numbers repeat.

Skipped when no headless server is installed. Cases run in parallel.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
from draftsman.blueprintable import Blueprint
from draftsman.entity import new_entity

from blueprint_smith import checks, effects, harness
from blueprint_smith.generators import Port
from blueprint_smith.harness import Probe
from blueprint_smith.pipeline import origin

pytestmark = pytest.mark.harness

L, BELT, INSERTER, LONG = "legendary", "turbo-transport-belt", "stack-inserter", "long-handed-inserter"
WINDOW = 3600
RATES = effects.LEGENDARY_STACK_INSERTER
LONG_RATES = effects.LEGENDARY_LONG_INSERTER
# a 4x4 plant at tiles 0-3 takes up to 4 beacons without them reaching anything else in these layouts
BEACONS = [(-3, 0), (-3, 3), (0, -3), (0, 4)]
# 11 beacons: a column on each side of the plant (the east one past the belt at x=5), and 3 more north and south
MIXED_BEACONS = [(-3, y) for y in (-5, -2, 1, 4)] + [(6, y) for y in (-5, -2, 1, 4)] + [(0, -3), (0, 4), (3, 4)]


def plant(at, recipe):
    e = new_entity("electromagnetic-plant", tile_position=at, quality=L, recipe=recipe)
    e.request_modules("productivity-module-3", range(5), quality=L)
    return e


def beacon(at):
    e = new_entity("beacon", tile_position=at, quality=L)
    e.request_modules("speed-module-3", (0, 1), quality=L)
    return e


def inserters(n, direction, name=INSERTER):
    """n inserters (stack by default) down the plant's east edge (x=4), picking up from `direction`."""
    return [new_entity(name, tile_position=(4, y), direction=direction, quality=L) for y in range(n)]


def blueprint(*entities, substation=(-5, -5)) -> Blueprint:
    bp = Blueprint()
    for e in entities:
        bp.entities.append(e)
    bp.entities.append(new_entity("substation", tile_position=substation))
    bp.generate_power_connections(only_axis=True)
    assert [p for check in checks.ALL_CHECKS for p in check(bp)] == []
    return bp


def tile(bp, x, y):
    """A tile in the frame ports and probes use: relative to the blueprint's top-left."""
    ox, oy = origin(bp)
    return x - ox, y - oy


def belt_to_plant(recipe, item, feed):
    """A full stacked belt (x=5, flowing south, dead end) -> 1 inserter -> a 4-beacon plant faster than it."""
    bp = blueprint(plant((0, 0), recipe), *map(beacon, BEACONS), *inserters(1, 4),
                   *(new_entity(BELT, tile_position=(5, y), direction=8) for y in range(-2, 4)))
    return bp, [Port("input", item, BELT, tile(bp, 5, -2), 8, 240, 4)], [Probe(tile(bp, 1, 1), feed, drain=True)]


def long_to_plant(n):
    """A full stacked copper belt 2 tiles out (x=6, nothing at x=5) -> n long-handed inserters -> a 4-beacon cable
    plant far faster than them."""
    bp = blueprint(plant((0, 0), "copper-cable"), *map(beacon, BEACONS), *inserters(n, 4, LONG),
                   *(new_entity(BELT, tile_position=(6, y), direction=8) for y in range(-2, 4)))
    return bp, [Port("input", "copper-plate", BELT, tile(bp, 6, -2), 8, 240, 4)], [Probe(tile(bp, 1, 1), (), drain=True)]


def mixed_belt_to_plant():
    """Green and plastic side-loaded from opposite sides onto one stacked belt (F3: x=5, flowing south, dead end), so
    each lane carries one item -> 1 inserter -> a red plant sped up past it (5 speed modules, 11 beacons), its cable
    fed and its output drained by script. A port feeds one item, hence the two feeder belts at y=-6."""
    red = new_entity("electromagnetic-plant", tile_position=(0, 0), quality=L, recipe="advanced-circuit")
    red.request_modules("speed-module-3", range(5), quality=L)
    bp = blueprint(red, *map(beacon, MIXED_BEACONS), *inserters(1, 4),
                   *(new_entity(BELT, tile_position=(5, y), direction=8) for y in range(-6, 4)),
                   *(new_entity(BELT, tile_position=(x, -6), direction=4) for x in (3, 4)),
                   *(new_entity(BELT, tile_position=(x, -6), direction=12) for x in (6, 7)),
                   new_entity("substation", tile_position=(-1, 7)), substation=(-1, -8))
    ports = [Port("input", "electronic-circuit", BELT, tile(bp, 3, -6), 4, 240, 4),
             Port("input", "plastic-bar", BELT, tile(bp, 7, -6), 12, 240, 4)]
    return bp, ports, [Probe(tile(bp, 1, 1), ("copper-cable",), drain=True)]


def plant_to_plant():
    """A cable plant fed copper (2 beacons) -> 1 inserter -> a circuit plant fed iron and drained (4 beacons)."""
    bp = blueprint(plant((0, 0), "copper-cable"), beacon((-3, 0)), beacon((-3, 3)), *inserters(1, 12),
                   plant((5, 0), "electronic-circuit"), *map(beacon, [(9, 0), (9, 3), (8, -3), (8, 6)]),
                   substation=(4, -3))
    return bp, [], [Probe(tile(bp, 1, 1), ("copper-plate",)), Probe(tile(bp, 6, 1), ("iron-plate",), drain=True)]


def plant_to_belt(n):
    """A circuit plant fed by script (2 beacons, 250/s) -> n inserters -> a stacked belt (x=5) out at the bottom."""
    bp = blueprint(plant((0, 0), "electronic-circuit"), beacon((-3, 0)), beacon((-3, 3)), *inserters(n, 12),
                   *(new_entity(BELT, tile_position=(5, y), direction=8) for y in range(8)))
    ports = [Port("output", "electronic-circuit", BELT, tile(bp, 5, 7), 8, 240, 4)]
    return bp, ports, [Probe(tile(bp, 1, 1), ("iron-plate", "copper-cable"))]


def plant_speed(n):
    """A circuit plant with n beacons, fed and drained by script, so only its own speed limits it."""
    bp = blueprint(plant((0, 0), "electronic-circuit"), *map(beacon, BEACONS[:n]))
    return bp, [], [Probe(tile(bp, 1, 1), ("iron-plate", "copper-cable"), drain=True)]


CASES = {
    "belt>circuit": lambda: belt_to_plant("electronic-circuit", "iron-plate", ("copper-cable",)),
    "belt>cable": lambda: belt_to_plant("copper-cable", "copper-plate", ()),
    "long>cable x1": lambda: long_to_plant(1),
    "long>cable x2": lambda: long_to_plant(2),
    "mixed>red": mixed_belt_to_plant,
    "plant>plant": plant_to_plant,
    "plant>belt x1": lambda: plant_to_belt(1),
    "plant>belt x2": lambda: plant_to_belt(2),
    **{f"speed N={n}": (lambda n=n: plant_speed(n)) for n in (1, 2, 4)},
}


def need_server():
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")


@pytest.fixture(scope="module")
def runs() -> dict[str, tuple[Blueprint, list[harness.HarnessResult]]]:
    need_server()
    jobs = {name: make() for name, make in CASES.items()}
    # serially: draftsman records warnings process-wide, and each case runs twice at once below
    strings = {name: bp.to_string() for name, (bp, _, _) in jobs.items()}

    def go(key):
        _, ports, probes = jobs[key[0]]
        return key, harness.run(strings[key[0]], ports, probes=probes, research="all", warmup_ticks=600,
                                window_ticks=WINDOW)

    keys = [(name, i) for name in jobs for i in range(2)]
    with ThreadPoolExecutor(len(keys)) as ex:
        done = dict(ex.map(go, keys))
    return {name: (jobs[name][0], [done[name, 0], done[name, 1]]) for name in jobs}


def only_working(statuses):
    return statuses == {"working": WINDOW}


@pytest.mark.parametrize("name", CASES)
def test_measurements_repeat_within_2_percent(runs, name):
    _, (a, b) = runs[name]
    assert a.build == b.build == harness.BuildStatus(0, 0, [])
    for x, y in zip(a.inserters, b.inserters, strict=True):
        assert x.rate == pytest.approx(y.rate, rel=0.02)
    for x, y in zip(a.machines, b.machines, strict=True):
        assert x.crafts == pytest.approx(y.crafts, rel=0.02)


@pytest.mark.parametrize("name", ["belt>circuit", "belt>cable"])
def test_one_inserter_takes_87_per_second_from_a_full_stacked_belt(runs, name):
    """The inserter never waits and the plant waits on it, so the inserter is what's measured."""
    _, (r, _) = runs[name]
    (i,) = r.inserters
    (m,) = r.machines
    assert i.rate == pytest.approx(RATES["belt_to_machine"], rel=0.02)
    assert (i.quality, i.hand) == (L, 16)
    assert only_working(i.statuses)
    assert m.statuses.get("item_ingredient_shortage", 0) > 0.2 * WINDOW


def per_second(n):
    return n / (WINDOW / 60)


@pytest.mark.parametrize("n", [1, 2])
def test_long_handed_inserters_take_13_per_second_each_from_a_full_stacked_belt(runs, n):
    """Its researched hand (1 + 3) is one belt stack. Two on the same plant edge add up: neither slows the other."""
    _, (r, _) = runs[f"long>cable x{n}"]
    (m,) = r.machines
    assert len(r.inserters) == n
    for i in r.inserters:
        assert i.rate == pytest.approx(LONG_RATES["belt_to_machine"], rel=0.02)
        assert (i.name, i.quality, i.hand) == (LONG, L, 4)
        assert only_working(i.statuses)
    assert m.statuses.get("item_ingredient_shortage", 0) > 0.5 * WINDOW
    # a cable craft eats 1 copper; products_finished counts productivity's bonus crafts too (F18)
    assert per_second(m.crafts) / (1 + m.productivity) == pytest.approx(n * LONG_RATES["belt_to_machine"], rel=0.02)


def test_one_inserter_takes_87_per_second_from_a_mixed_belt(runs):
    """Green on one lane and plastic on the other: the hand holds one item, so a swing takes from one lane only,
    yet it moves as much as from a one-item belt. The harness counts an inserter's items, not which item: the split
    comes from the plant, which eats 2 green and 2 plastic a craft, so over the window it took half of each."""
    bp, (r, _) = runs["mixed>red"]
    (i,) = r.inserters
    (m,) = r.machines
    (entity, beacons), = checks.beacon_targets(bp).items()
    want = effects.entity_rates(entity, beacons=beacons, research="all")
    demand = want.ingredients["electronic-circuit"] + want.ingredients["plastic-bar"]
    assert len(beacons) == len(MIXED_BEACONS) and demand > 1.05 * RATES["mixed_belt_to_machine"]  # the plant is faster
    assert m.crafting_speed == pytest.approx(want.crafting_speed, rel=1e-6)
    assert i.rate == pytest.approx(RATES["mixed_belt_to_machine"], rel=0.02)
    assert (i.quality, i.hand) == (L, 16)
    assert only_working(i.statuses)
    assert m.statuses.get("item_ingredient_shortage", 0) > 0.02 * WINDOW  # the plant waits on the inserter
    green = plastic = 2 * per_second(m.crafts) / (1 + m.productivity)
    assert green + plastic == pytest.approx(i.rate, rel=0.02)


def test_one_inserter_moves_120_per_second_between_plants(runs):
    _, (r, _) = runs["plant>plant"]
    (i,) = r.inserters
    cable, circuit = r.machines
    assert i.rate == pytest.approx(RATES["machine_to_machine"], rel=0.02)
    assert only_working(i.statuses)
    assert cable.statuses.get("full_output", 0) > 0.5 * WINDOW  # supply to spare
    assert circuit.statuses.get("item_ingredient_shortage", 0) > 0.5 * WINDOW  # room to spare
    # products_finished counts crafts (productivity's bonus crafts included), not items: 2 cables a craft
    assert cable.crafts * 2 / (WINDOW / 60) == pytest.approx(i.rate, rel=0.02)


def test_one_inserter_puts_80_per_second_on_the_far_lane_only(runs):
    _, (r, _) = runs["plant>belt x1"]
    (i,) = r.inserters
    (o,) = r.outputs
    assert i.rate == pytest.approx(RATES["machine_to_belt"], rel=0.02)
    assert o.lane_rates == pytest.approx([RATES["machine_to_belt"], 0], abs=1)  # lane 1 is the left, east here (F1)
    assert r.machines[0].statuses.get("full_output", 0) > 0.5 * WINDOW  # the plant makes more than it takes


def test_a_second_inserter_on_the_same_lane_only_fills_it_to_120(runs):
    _, (r, _) = runs["plant>belt x2"]
    first, second = r.inserters
    (o,) = r.outputs
    lane = effects.research_bonuses("all").belt_stack_size_bonus + 1
    assert lane == 4
    assert o.lane_rates == pytest.approx([30 * lane, 0], abs=1)  # a full stacked turbo lane: 120/s
    assert first.rate == pytest.approx(RATES["machine_to_belt"], rel=0.02)
    assert second.rate == pytest.approx(30 * lane - RATES["machine_to_belt"], rel=0.02)


@pytest.mark.parametrize("n", [1, 2, 4])
def test_the_solver_matches_a_plant_with_n_beacons_within_1_percent(runs, n):
    """The engine reports crafting speed exactly, so holding it to 1e-6 also tests effects.py's 2.0 rounding (F19):
    2 beacons give 45.45, where unrounded maths gives 45.44375. Output has window noise, so it gets the plan's 1%."""
    bp, (r, _) = runs[f"speed N={n}"]
    (entity, beacons), = checks.beacon_targets(bp).items()
    assert len(beacons) == n
    want = effects.entity_rates(entity, beacons=beacons, research="all")
    (m,) = r.machines
    assert only_working(m.statuses)
    assert m.crafting_speed == pytest.approx(want.crafting_speed, rel=1e-6)
    assert m.productivity == pytest.approx(want.productivity, rel=1e-6)
    assert m.crafts / (WINDOW / 60) == pytest.approx(want.products["electronic-circuit"], rel=0.01)
