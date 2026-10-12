"""plant_array (M2b, docs/red-circuits-plan.md): the generic beaconed plant array built for red circuits. Its layout,
ports and beacon counts, the sizing behind its defaults and notes, the optimiser's variants, one near item (green
circuits) as well as two, the flow check with a mutation per technique, and harness runs of the default red block,
an under-sized one and the optimiser's pick."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from draftsman.constants import Direction
from draftsman.entity import new_entity

from blueprint_smith import checks, generators, harness
from blueprint_smith import optimise as opt
from blueprint_smith.errors import BuildError, SpecError
from blueprint_smith.evaluate import evaluate
from blueprint_smith.generators import plant_array as pa
from blueprint_smith.harness.verdict import BLOCKED, feeds_only_machines, share
from blueprint_smith.pipeline import build

SPEC = {"type": "plant_array"}
REQUEST = {"item": "advanced-circuit", "rate": 240}
RED, CABLE = "advanced-circuit", "copper-cable"
N, E, S, W = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST


def _at(e) -> tuple[int, int]:
    return e.tile_position.x, e.tile_position.y


def _plants(bp, recipe) -> list:
    return sorted((e for e in bp.entities if e.name == pa.PLANT and e.recipe == recipe), key=lambda e: (_at(e)[1], _at(e)[0]))


def test_the_default_red_block_builds_clean():
    r = build(SPEC)
    assert opt.footprint(r.blueprint) == (42 + 3, 21)  # and the output's lane balancer (P4)
    assert [_at(e) for e in _plants(r.blueprint, RED)] == [(0, 0), (10, 0), (14, 0), (24, 0),
                                                           (0, 11), (10, 11), (14, 11), (24, 11)]
    assert [_at(e) for e in _plants(r.blueprint, CABLE)] == [(5, 0), (19, 0), (5, 11), (19, 11)]
    assert not [n for n in r.notes if n.startswith("WARNING")]


def test_ports_are_stacked_at_the_west_and_east_edges():
    ports = {p.item: p for p in build(SPEC).ports}
    assert {(item, p.role, p.tile, p.direction, p.stack) for item, p in ports.items()} == {
        ("copper-plate", "input", (0, 0), int(E), 4),
        ("electronic-circuit", "input", (0, 3), int(E), 4),
        ("plastic-bar", "input", (0, 6), int(E), 4),
        (RED, "output", (41 + 3, 10), int(E), 4),  # the end of the output's lane balancer (P4)
    }
    assert ports[RED].rate == 240
    # what the block eats at 240/s: 2 green and 2 plastic a craft, 4 cable from 1 copper per 2 (both at +175%)
    assert ports["electronic-circuit"].rate == pytest.approx(240 * 2 / 2.75)
    assert ports["plastic-bar"].rate == pytest.approx(240 * 2 / 2.75)
    assert ports["copper-plate"].rate == pytest.approx(240 * 4 / 2.75 / 2 / 2.75)


def test_beacon_counts_match_the_beacon_reach_check():
    """The sizing counts each plant's beacons from the geometry; checks.beacon_targets must agree (F24)."""
    bp = build(SPEC).blueprint
    targets = checks.beacon_targets(bp)
    assert [len(targets[e]) for e in _plants(bp, RED)] == [4, 4, 4, 5] * 2
    assert [len(targets[e]) for e in _plants(bp, CABLE)] == [4, 4] * 2
    products, middles = pa.beacon_counts(pa.row_layout(4), east_beacon=True)
    assert products == {0: 4, 10: 4, 14: 4, 24: 5} and middles == {5: 4, 19: 4}


def test_the_default_is_sized_by_the_solver_and_the_measured_rates():
    r = build(SPEC)
    assert "beacons per product plant, west to east: 4, 4, 4, 5; each row can make 120.27/s and delivers " \
           "120.00/s (120/s wanted)" in r.notes
    names = {e.name for e in r.blueprint.entities}
    assert {pa.LONG, pa.SPLITTER, pa.UNDERGROUND, pa.POLE} <= names
    inserters = [e for e in r.blueprint.entities if e.name in (pa.INSERTER, pa.LONG)]
    by_row = {}
    for e in inserters:
        by_row.setdefault((e.name, _at(e)[1]), []).append(_at(e)[0])
    assert by_row[(pa.INSERTER, -1)] == [1, 10, 15, 24]  # 1 near inserter a red plant (87.47/s, F30)
    assert by_row[(pa.LONG, -1)] == [5, 6, 19, 20]  # 2 long-handed a cable plant (2 x 13.33/s, F29)
    assert by_row[(pa.INSERTER, 4)] == [2, 3, 11, 12, 16, 17, 26, 27]  # 2 output inserters a red plant (T7)
    assert sorted(x for (name, y), xs in by_row.items() if 0 <= y <= 3 for x in xs) == [4, 9, 18, 23]


def test_one_output_inserter_is_warned_about_on_a_filling_lane():
    """The last plant drops onto a lane its row has filled to 73%: one inserter gets too few free slots (T7)."""
    notes = build({**SPEC, "output_inserters": 1}).notes
    assert any(n.startswith("WARNING: advanced-circuit plant -> output lane (the last plant's free slots) carries "
                            "21.69/s") for n in notes)
    assert "WARNING: the block delivers 218.44/s, under the 240/s target" in notes


def test_one_near_item_builds_green_circuits():
    r = build({**SPEC, "item": "electronic-circuit", "rate": 120})
    assert {p.item for p in r.ports if p.role == "input"} == {"copper-plate", "iron-plate"}
    tiles = {_at(e): e for e in r.blueprint.entities}
    assert pa.M_X + 1 not in {x for (x, y) in tiles if y == pa.IN_Y and tiles[(x, y)].name == pa.BELT}
    assert len([e for e in r.blueprint.entities if e.name == pa.SPLITTER]) == 2 + 1  # and the output's (P4)


def test_green_circuits_at_a_full_belt_are_left_to_the_circuit_block():
    """One green plant makes 350/s: any row would sit blocked on a full lane, so the array offers no variant."""
    assert pa.variants({"item": "electronic-circuit", "rate": 240}) == []
    assert any("would sit blocked on output" in n
               for n in build({**SPEC, "item": "electronic-circuit", "rate": 240}).notes)


def test_variants_are_the_solver_approved_inserter_counts():
    found = pa.variants(REQUEST)
    assert found and all(v["plants_per_row"] == 4 and v["east_beacon"] for v in found)
    assert {v["output_inserters"] for v in found} == {2}
    assert {v["far_inserters"] for v in found} == {2, 3, 4}
    default = {**SPEC, "item": RED, "rate": 240, "plants_per_row": 4, "east_beacon": True, "near_inserters": 1,
               "hand_inserters": 1, "far_inserters": 2, "output_inserters": 2}
    assert default in found
    for v in found[:3]:
        build(v)


@pytest.mark.parametrize("request_", [
    {"item": "iron-gear-wheel", "rate": 10}, {"item": RED, "rate": 0}, {"item": RED, "rate": 241},
    {"item": RED, "rate": True},
])
def test_no_variants_for_what_it_cannot_make(request_):
    assert pa.variants(request_) == []


@pytest.mark.parametrize("bad", [
    {"item": "iron-gear-wheel"}, {"rate": 0}, {"rate": 300}, {"plants_per_row": 9}, {"east_beacon": "yes"},
    {"near_inserters": 3}, {"far_inserters": 0}, {"output_inserters": 3}, {"quality": "shiny"},
])
def test_spec_errors(bad):
    with pytest.raises(SpecError):
        build({**SPEC, **bad})


# --- the flow check: one mutation per technique ---------------------------------------------------------------

def _mutated(monkeypatch, mutate):
    orig = generators.REGISTRY["plant_array"]

    def wrapper(spec):
        entities, notes, ports = orig(spec)
        mutate(entities)
        return entities, notes, ports

    monkeypatch.setitem(generators.REGISTRY, "plant_array", wrapper)


def _drop(*tiles, name=pa.BELT):
    return lambda es: es.__setitem__(slice(None), [e for e in es if not (e.name == name and _at(e) in tiles)])


def _turn(tile, direction, name=pa.BELT):
    return lambda es: [setattr(e, "direction", direction) for e in es if e.name == name and _at(e) == tile]


def _add(name, tile, direction):
    return lambda es: es.append(new_entity(name, tile_position=tile, direction=direction))


def _priority(tile, priority):
    return lambda es: [setattr(e, "output_priority", priority) for e in es if e.name == pa.SPLITTER and _at(e) == tile]


def _swap(tile, name):
    def mutate(es):
        for i, e in enumerate(es):
            if _at(e) == tile and e.name in (pa.INSERTER, pa.LONG):
                es[i] = new_entity(name, tile_position=tile, direction=e.direction)
    return mutate


@pytest.mark.parametrize("mutate, message", [
    # T8: plastic no longer side-loads row A's riser, so green would take both lanes
    (_drop((-1, -1)), "row A: no belt at (-1, -1) side-loading the riser from the east"),
    # T8: a belt feeding the riser from behind turns the T into a straight belt
    (_add(pa.BELT, (-2, 0), N), "row A: a belt feeds the riser at (-2, -1) from behind"),
    # T8, row B: plastic no longer side-loads row B's riser under the band
    (_drop((-1, 10)), "row B: no belt at (-1, 10) side-loading the riser from the east"),
    # row B's merged near belt broken on its way down x=-2
    (_drop((-2, 12)), "row B: no belt at (-2, 12) flowing south from its riser to its near belt"),
    # T9: output B's turn-in is gone, so the merge tile curves and row B never joins
    (_drop((33, 8)), "no belt at (33, 8) bringing output B north into the merge"),
    (_turn((33, 6), E), "no belt at (33, 6) bringing output A south into the merge"),
    (_turn((33, 7), S), "no belt at (33, 7) flowing east for both outputs to side-load"),
    (_turn((33, 5), E), "must turn output A south into the merge"),
    (_turn((33, 9), E), "must turn output B north into the merge"),
    # T12: the lane reset without priority splits evenly, so half the far lane stays full
    (_priority((13, 4), "none"), "row A: the lane reset turbo-splitter at (13.5, 5.0) must prioritise its inserter-side"),
    (_priority((13, 9), "left"), "row B: the lane reset turbo-splitter at (13.5, 10.0) must prioritise its inserter-side"),
    # T12: the priority half has no way back onto the output belt
    (_drop((14, 4)), "row A: no belt at (14, 4) flowing south to side-load the lane reset's priority half"),
    # T12: no lane reset at all
    (_drop((13, 9), name=pa.SPLITTER), "row B: 0 lane reset splitters on its output belt at y=9, not 1"),
    # an output inserter turned round unloads output A into a red plant
    (_turn((2, 4), S, name=pa.INSERTER), "moves items from output belt to product plant"),
    # a hand-off gap without its inserters: the first red plant of each row gets no cable
    (_drop((4, 0), (4, 14), name=pa.INSERTER), "has no inserter moving items from intermediate plant to product plant"),
    # T10: a stack inserter can't reach over the near belt; it feeds the cable plant from the near belt instead
    (_swap((5, -1), pa.INSERTER), "moves items from near belt to intermediate plant"),
    (_turn((3, -2), W), "on the near belt must flow east"),
])
def test_broken_layout_is_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, mutate)
    with pytest.raises(BuildError) as err:
        build(SPEC)
    assert any(message in p for p in err.value.problems), err.value.problems


def test_the_unmutated_wrapper_builds(monkeypatch):
    _mutated(monkeypatch, lambda es: None)
    build(SPEC)


# --- the harness (real server; skipped without one) ---------------------------------------------------------

HARNESS_SPECS = {"default": SPEC, "one output inserter": {**SPEC, "output_inserters": 1}}


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
def test_the_default_red_block_fills_a_stacked_turbo_belt(runs):
    ev = runs["default"]
    assert ev.verdict.passed, "\n".join(ev.verdict.problems)
    (o,) = ev.result.outputs
    assert o.produced_rate >= 0.98 * 240
    assert o.lane_rates == pytest.approx([120, 120], rel=0.02)
    reds = [m for m in ev.result.machines if m.recipe == RED]
    cables = [m for m in ev.result.machines if m.recipe == CABLE]
    assert len(reds) == 8 and len(cables) == 4
    assert all(feeds_only_machines(m) for m in cables) and not any(feeds_only_machines(m) for m in reds)
    # the lane reset (T12) leaves no red plant waiting on a full lane: 1.1% blocked at most without it
    assert max(share(m, BLOCKED, ev.window_ticks) for m in reds) <= 0.01


@pytest.mark.harness
def test_one_output_inserter_a_plant_still_backs_up_with_the_lane_reset(runs):
    """T7, T12: with the lane reset one output inserter a plant makes the rate with both lanes full (without it, it
    fell to 97.2%), but a plant's output still grows past the bar, so 2 a plant stay the default."""
    ev = runs["one output inserter"]
    assert not ev.verdict.passed
    (o,) = ev.result.outputs
    assert o.produced_rate >= 0.98 * 240
    assert o.lane_rates == pytest.approx([120, 120], rel=0.02)
    assert any("output backing up" in p for p in ev.verdict.problems), ev.verdict.problems


@pytest.mark.harness
def test_the_optimiser_picks_a_passing_red_block(runs):  # `runs` only to skip without a server
    found = opt.optimise(REQUEST)
    assert found.winner is not None
    assert found.winner.spec["type"] == "plant_array"
    assert found.winner.evaluation.verdict.passed
