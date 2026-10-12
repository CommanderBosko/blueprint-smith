import json
import math
from pathlib import Path

import pytest
from draftsman.blueprintable import Blueprint
from draftsman.constants import Direction

from blueprint_smith import checks, ratios
from blueprint_smith.errors import BuildError, SpecError
from blueprint_smith.pipeline import build

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_iron_and_steel_furnaces_pair_one_to_one():
    # 0.625 iron plates/s out of one furnace is exactly what one steel furnace eats
    assert ratios.crafts_per_second("electric-furnace", "iron-plate") == pytest.approx(0.625)
    assert ratios.ingredients_per_second("electric-furnace", "steel-plate") == {"iron-plate": pytest.approx(0.625)}


@pytest.mark.parametrize("count", [1, 2, 3, 12])
def test_column_builds_and_round_trips(count):
    r = build({"type": "steel_column", "count": count})
    kinds = [e.name for e in r.blueprint.entities]
    modules = math.ceil(count / 2)
    assert kinds.count("electric-furnace") == 2 * count  # an iron and a steel furnace per pair
    assert kinds.count("fast-inserter") == 3 * count
    # 6 ore belt + 6 steel belt per module, and 6 in the output's lane balancer (P4)
    assert kinds.count("transport-belt") == 12 * modules + 6
    assert kinds.count("medium-electric-pole") == 3 * modules
    # steel never fills one lane, so no lane balancing (T1) inside: the only splitter is the output's (P4)
    assert kinds.count("splitter") == 1
    assert Blueprint.from_string(r.string).to_string() == r.string


def test_full_yellow_belt_of_ore_makes_3_steel():
    r = build({"type": "steel_column", "rate": 3})
    assert [e.name for e in r.blueprint.entities].count("electric-furnace") == 48
    assert "3.000 steel-plate/s from 15.000 iron-ore/s" in r.notes[0]
    assert not any("WARNING" in n for n in r.notes)
    over = build({"type": "steel_column", "count": 25})
    assert any("iron-ore demand 15.62/s exceeds the input transport-belt capacity (15.00/s)" in n for n in over.notes)


def test_example_spec_builds():
    spec = json.loads((EXAMPLES / "steel_column.json").read_text())
    assert len(build(spec).blueprint.find_entities_filtered(name="electric-furnace")) == 48


def test_module_layout():
    bp = build({"type": "steel_column", "count": 2}).blueprint

    def at(x, y):
        return [e.name for e in bp.find_entities_filtered(position=(x + 0.5, y + 0.5))]

    assert at(1, 1) == at(5, 1) == at(9, 1) == ["medium-electric-pole"]
    for x in (1, 5, 9):
        assert at(x, 2) == at(x, 3) == ["fast-inserter"]
        assert at(x, 0) == at(x, 4) == at(x, 5) == []
    for y in range(6):
        assert at(0, y) == at(10, y) == ["transport-belt"]
        assert at(3, y) == at(7, y) == ["electric-furnace"]


def test_odd_count_leaves_last_module_half_empty():
    bp = build({"type": "steel_column", "count": 3}).blueprint
    assert len(bp.find_entities_filtered(name="electric-furnace")) == 6
    assert not bp.find_entities_filtered(position=(3.5, 10.5))  # where the 4th iron furnace would sit
    assert not bp.find_entities_filtered(position=(7.5, 10.5))


def test_inserters_move_west_to_east():
    bp = build({"type": "steel_column", "count": 2}).blueprint
    for ins in bp.find_entities_filtered(name="fast-inserter"):
        (px, _), (dx, _) = ins.pickup_position, ins.drop_position
        assert px < dx


@pytest.mark.parametrize("count", [1, 3, 12])
def test_poles_form_one_network(count):
    bp = build({"type": "steel_column", "count": count}).blueprint
    modules = math.ceil(count / 2)
    # each module's 3 poles join each other (1-5, 5-9 and 1-9, all within reach 9); 3 rails run between modules
    assert len(bp.wires) == 3 * modules + 3 * (modules - 1)
    assert checks.pole_network(bp) == []


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"count": 2, "rate": 3},
        {"rate": "3"},
        {"rate": 0},
        {"count": 0},
        {"count": 2.0},
        {"count": 2, "furnace": "steel-furnace"},  # 2x2
        {"count": 2, "belt": "iron-chest"},
        {"count": 2, "inserter": "transport-belt"},
        {"count": 2, "pole": "iron-chest"},
    ],
)
def test_spec_errors(bad):
    with pytest.raises(SpecError):
        build({"type": "steel_column", **bad})


def _mutated(monkeypatch, mutate):
    from blueprint_smith import generators

    orig = generators.REGISTRY["steel_column"]

    def wrapper(spec):
        entities, notes, ports = orig(spec)
        mutate(entities)
        return entities, notes, ports

    monkeypatch.setitem(generators.REGISTRY, "steel_column", wrapper)


def _drop(pred):
    return lambda entities: entities.__setitem__(slice(None), [e for e in entities if not pred(e)])


def _col(e):
    return math.floor(e.global_position[0])


@pytest.mark.parametrize(
    "mutate, message",
    [
        # every inserter flipped to pick up from the east
        (lambda es: [setattr(e, "direction", Direction.EAST) for e in es if e.name == "fast-inserter"], "moves the wrong way"),
        # the iron -> steel hand-off reversed on one pair only
        (lambda es: setattr(next(e for e in es if e.name == "fast-inserter" and _col(e) == 5), "direction", Direction.EAST),
         "moves the wrong way"),
        # no hand-off: iron furnaces fill up and steel furnaces starve
        (_drop(lambda e: e.name == "fast-inserter" and _col(e) == 5), "needs an inserter loading it and one unloading it"),
        # a steel furnace missing from its pair
        (_drop(lambda e: e.name == "electric-furnace" and tuple(e.global_position) == (7.5, 4.5)), "has no partner"),
        (lambda es: [setattr(e, "direction", Direction.NORTH) for e in es if e.name == "transport-belt" and _col(e) == 10],
         "must flow south"),
        # without the middle pole, the hand-off inserters are out of reach of the outer poles
        (_drop(lambda e: e.name == "medium-electric-pole" and _col(e) == 5), "not covered by any electric pole"),
    ],
)
def test_broken_layout_is_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, mutate)
    with pytest.raises(BuildError) as ei:
        build({"type": "steel_column", "count": 2})
    assert any(message in p for p in ei.value.problems)
