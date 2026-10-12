import dataclasses
import json
from pathlib import Path

import pytest
from draftsman.entity import new_entity

from blueprint_smith import generators, pipeline
from blueprint_smith.errors import BuildError
from blueprint_smith.generators import Port
from blueprint_smith.pipeline import DIRECTION, LABEL, build, origin

EXAMPLES = Path(__file__).parent.parent / "examples"
STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
BELT_TYPES = {"transport-belt", "underground-belt", "splitter", "loader", "loader-1x1", "linked-belt"}

# example -> (input item, input rate, output item, output tile, output rate, belt); each output ends its lane
# balancer (P4), 3 tiles past the generator's last plate belt
EXPECTED = {
    "smelting_column.json": ("iron-ore", 15.0, "iron-plate", (6, 74), 15.0, "transport-belt"),
    "smelting_column_copper.json": ("copper-ore", 30.0, "copper-plate", (6, 146), 30.0, "fast-transport-belt"),
    "smelting_column_steel.json": ("iron-plate", 15.0, "steel-plate", (6, 74), 3.0, "transport-belt"),
    "steel_column.json": ("iron-ore", 15.0, "steel-plate", (10, 74), 3.0, "transport-belt"),
}
# examples with more than one input, whose exact ports their own tests check
COVERED_ELSEWHERE = {"circuit_block.json": "tests/test_circuit_block.py",
                     "circuit_block_north.json": "tests/test_circuit_block.py"}
SPECS = [
    *(json.loads(p.read_text()) for p in sorted(EXAMPLES.glob("*.json"))),
    *({"type": t, "count": n} for t in ("smelting_column", "steel_column") for n in (1, 2, 3)),
    {"type": "smelting_column", "recipe": "stone-brick", "count": 2, "belt": "express-transport-belt"},
]


def _belts_at(bp, x, y):
    return [e for e in bp.find_entities_filtered(position=(x + 0.5, y + 0.5)) if e.prototype.get("type") in BELT_TYPES]


def test_every_example_is_covered():
    assert sorted(p.name for p in EXAMPLES.glob("*.json")) == sorted([*EXPECTED, *COVERED_ELSEWHERE])


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: f"{s['type']}-{s.get('count', s.get('rate'))}")
def test_ports_sit_on_the_belt_ends(spec):
    r = build(spec)
    bp = r.blueprint
    assert [p.role for p in r.ports].count("output") == 1 and "input" in [p.role for p in r.ports]
    # port tiles are relative to the block's top-left tile, which leaves out the input labels
    ox, oy = origin(bp)
    assert (ox, oy) == (min(e.tile_position.x for e in bp.entities if e.name != LABEL),
                        min(e.tile_position.y for e in bp.entities if e.name != LABEL))
    for port in r.ports:
        sign = -1 if port.role == "input" else 1
        x, y = port.tile[0] + ox, port.tile[1] + oy
        (belt,) = _belts_at(bp, x, y)
        assert belt.name == port.belt == spec.get("belt", port.belt)
        assert belt.direction == port.direction
        dx, dy = STEP[port.direction]
        # nothing feeds the input's first tile from behind; nothing takes the output's last tile further
        assert _belts_at(bp, x + sign * dx, y + sign * dy) == []


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_ports(name):
    spec = json.loads((EXAMPLES / name).read_text())
    in_item, in_rate, out_item, out_tile, out_rate, belt = EXPECTED[name]
    inp, out = build(spec).ports
    assert inp == Port("input", in_item, belt, (0, 0), 8, pytest.approx(in_rate))
    assert out == Port("output", out_item, belt, out_tile, 8, pytest.approx(out_rate))
    assert type(out.direction) is int and type(out.rate) is float
    assert inp.stack == out.stack == 1  # M1 generators: plain belts, fed and drained by loaders


def test_output_rate_without_a_target_is_what_the_machines_make():
    # 3 furnaces x 0.625 plates/s; 3 pairs x 0.125 steel/s
    assert build({"type": "smelting_column", "count": 3}).ports[-1].rate == pytest.approx(1.875)
    assert build({"type": "steel_column", "count": 3}).ports[-1].rate == pytest.approx(0.375)


def _wrapped(monkeypatch, name, change, as_type=None):
    """Register generator `name`, its output passed through `change`, as `as_type` (default: in its place)."""
    orig = generators.REGISTRY[name]

    def wrapper(spec):
        entities, notes, ports = orig(spec)
        return change(entities, notes, ports)

    monkeypatch.setitem(generators.REGISTRY, as_type or name, wrapper)


@pytest.mark.parametrize("name", ["smelting_column", "steel_column"])
@pytest.mark.parametrize("dx, dy", [(3, 5), (-4, -7)])
def test_port_tiles_are_relative_to_the_top_left(monkeypatch, name, dx, dy):
    expected = build({"type": name, "count": 3}).ports

    def shift(entities, notes, ports):
        for e in entities:
            e.tile_position = (e.tile_position.x + dx, e.tile_position.y + dy)
        return entities, notes, [dataclasses.replace(p, tile=(p.tile[0] + dx, p.tile[1] + dy)) for p in ports]

    # under a new type: the generators' own check_flow expects their columns at x=0
    _wrapped(monkeypatch, name, shift, as_type="shifted")
    assert build({"type": "shifted", "count": 3}).ports == expected


def _change(role, changes):
    """Rewrite the generator's `role` port with the fields `changes(port)` returns."""

    def change(entities, notes, ports):
        return entities, notes, [dataclasses.replace(p, **changes(p)) if p.role == role else p for p in ports]

    return change


def _off(dx, dy):
    return lambda p: {"tile": (p.tile[0] + dx, p.tile[1] + dy)}


@pytest.mark.parametrize("name", ["smelting_column", "steel_column"])
@pytest.mark.parametrize(
    "role, changes, message",
    [
        # the output port one tile off the belt's end, each way
        ("output", _off(0, -1), {"smelting_column": "found splitter", "steel_column": "the belt doesn't end there"}),
        ("output", _off(0, 1), "no transport-belt on that tile"),
        ("output", _off(1, 0), "no transport-belt on that tile"),
        # smelting: the side-load belt, which flows east; steel: an empty row of the inserter column
        ("output", _off(-1, 0), {"smelting_column": "flows 4, not 8", "steel_column": "no transport-belt on that tile"}),
        ("input", _off(0, 1), "the belt doesn't start there"),
        ("input", _off(0, -1), "no transport-belt on that tile"),
        ("output", lambda p: {"direction": 4}, "flows 8, not 4"),
        ("input", lambda p: {"belt": "fast-transport-belt"}, "no fast-transport-belt on that tile"),
        ("output", lambda p: {"role": "outlet"}, "role must be"),
        ("input", lambda p: {"stack": 0}, "stack must be an integer from 1 to 4 (items per belt slot), got 0"),
        ("output", lambda p: {"stack": 5}, "stack must be an integer from 1 to 4 (items per belt slot), got 5"),
        ("input", lambda p: {"stack": 2.0}, "stack must be an integer from 1 to 4 (items per belt slot), got 2.0"),
    ],
)
def test_wrong_ports_are_rejected(monkeypatch, name, role, changes, message):
    if isinstance(message, dict):
        message = message[name]
    _wrapped(monkeypatch, name, _change(role, changes))
    with pytest.raises(BuildError) as ei:
        build({"type": name, "count": 2})
    assert any(message in p for p in ei.value.problems), ei.value.problems


def test_blocked_output_end_is_rejected(monkeypatch):
    # a chest past the plate belt's last tile: the port is still on the belt end, but nothing can drain it
    def block(entities, notes, ports):
        (out,) = [p for p in ports if p.role == "output"]
        return [*entities, new_entity("iron-chest", tile_position=(out.tile[0], out.tile[1] + 1))], notes, ports

    _wrapped(monkeypatch, "smelting_column", block)
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any("iron-chest sits next in line" in p for p in ei.value.problems)


@pytest.mark.parametrize("stack", [1, 2, 4])
def test_stacked_ports_are_accepted(monkeypatch, stack):
    _wrapped(monkeypatch, "smelting_column",
             lambda entities, notes, ports: (entities, notes, [dataclasses.replace(p, stack=stack) for p in ports]))
    assert [p.stack for p in build({"type": "smelting_column", "count": 2}).ports] == [stack, stack]


# P3: every input is labelled with a display panel showing its item, one free tile out from its first belt
@pytest.mark.parametrize("spec", [*SPECS, {"type": "plant_array"}],
                         ids=lambda s: f"{s['type']}-{s.get('count', s.get('rate', s.get('copper', 'default')))}")
def test_every_input_is_labelled(spec):
    r = build(spec)
    bp = r.blueprint
    ox, oy = origin(bp)
    inputs = [p for p in r.ports if p.role == "input"]
    panels = {(e.tile_position.x - ox, e.tile_position.y - oy): e.icon.name for e in bp.entities if e.name == LABEL}
    expected = {}
    for port in inputs:
        dx, dy = STEP[port.direction]
        expected[(port.tile[0] - 2 * dx, port.tile[1] - 2 * dy)] = port.item
        # the tile between stays free, where the supply belt comes in
        assert bp.find_entities_filtered(position=(port.tile[0] + ox - dx + 0.5, port.tile[1] + oy - dy + 0.5)) == []
    assert panels == expected


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda panels: [], "no display-panel showing iron-ore"),
        (lambda panels: [_shows(e, "copper-ore") for e in panels], "(found ['copper-ore'])"),
        # one tile too close: on the supply belt's tile, and not where the check looks
        (lambda panels: [_moved(e, 0, 1) for e in panels], "no display-panel showing iron-ore"),
    ],
)
def test_wrong_labels_are_rejected(monkeypatch, mutate, message):
    labels = pipeline.labels
    monkeypatch.setattr(pipeline, "labels", lambda ports: mutate(labels(ports)))
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any(message in p for p in ei.value.problems), ei.value.problems


def _shows(e, item):
    e.icon = {"type": "item", "name": item}
    return e


def _moved(e, dx, dy):
    e.tile_position = (e.tile_position.x + dx, e.tile_position.y + dy)
    return e


def test_labels_leave_the_ports_and_footprint_alone(monkeypatch):
    from blueprint_smith import optimise as opt

    with_labels = build({"type": "plant_array"})
    monkeypatch.setattr(pipeline, "labels", lambda ports: [])
    monkeypatch.setattr(pipeline, "check_labels", lambda bp, ports: [])
    without = build({"type": "plant_array"})
    assert with_labels.ports == without.ports
    assert opt.footprint(with_labels.blueprint) == opt.footprint(without.blueprint) == (45, 21)  # 42 + balancer


# P4: every belt output ends in a lane balancer of its belt's tier
@pytest.mark.parametrize("spec", [*SPECS, {"type": "plant_array"}],
                         ids=lambda s: f"{s['type']}-{s.get('count', s.get('rate', s.get('copper', 'default')))}")
def test_every_output_ends_in_a_lane_balancer(spec):
    r = build(spec)
    bp = r.blueprint
    ox, oy = origin(bp)
    (out,) = [p for p in r.ports if p.role == "output"]
    dx, dy = STEP[out.direction]
    rx, ry = -dy, dx  # the flow's right hand

    def at(forward, right):  # forward counts back from the balancer's end
        x, y = out.tile[0] + ox + forward * dx + right * rx, out.tile[1] + oy + forward * dy + right * ry
        return [(e.name, int(e.direction)) for e in bp.find_entities_filtered(position=(x + 0.5, y + 0.5))]

    d, right, left = out.direction, DIRECTION[(rx, ry)], DIRECTION[(-rx, -ry)]
    splitter = pipeline.SPLITTER[out.belt]
    assert at(-2, 0) == at(-2, 1) == [(splitter, d)]
    assert at(-1, 1) == [(out.belt, d)] and at(0, 1) == [(out.belt, left)]  # the right half: on, then in
    assert at(-1, 0) == [(out.belt, left)] and at(-1, -1) == [(out.belt, d)] and at(0, -1) == [(out.belt, right)]
    assert at(0, 0) == [(out.belt, d)]  # side-loaded from both sides
    # the generator's own last belt feeds the splitter
    assert [name for name, flow in at(-3, 0) if flow == d] != []


def _mutated(monkeypatch, mutate):
    balancers = pipeline.balancers

    def wrapper(ports):
        entities, moved = balancers(ports)
        return mutate(entities), moved

    monkeypatch.setattr(pipeline, "balancers", wrapper)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda es: [e for e in es if e.name != "splitter"], "needs a splitter flowing 8"),
        # the straight half side-loads nothing: it runs on past the end
        (lambda es: [_flowing(e, 8) if _tile(e) == (5, 74) else e for e in es], "needs a transport-belt flowing 4"),
        # the curved-out half missing its turn back in
        (lambda es: [e for e in es if _tile(e) != (7, 74)], "needs a transport-belt flowing 12"),
    ],
)
def test_wrong_balancers_are_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, mutate)
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 24})
    assert any(message in p for p in ei.value.problems), ei.value.problems


def _tile(e) -> tuple[int, int]:
    return e.tile_position.x, e.tile_position.y


def _flowing(e, direction):
    e.direction = direction
    return e
