import json
import math

import pytest
from draftsman.blueprintable import Blueprint
from draftsman.entity import new_entity
from draftsman.utils import string_to_JSON

from blueprint_smith import checks, ratios
from blueprint_smith.cli import main
from blueprint_smith.errors import BuildError, SpecError
from blueprint_smith.pipeline import build


def test_ratios_match_prototype_data():
    # electric furnace: crafting speed 2, iron plate 3.2s -> 0.625/s
    assert ratios.crafts_per_second("electric-furnace", "iron-plate") == pytest.approx(0.625)
    assert ratios.machines_for_rate("electric-furnace", "iron-plate", 7.5) == 12
    assert ratios.machines_for_rate("electric-furnace", "iron-plate", 7.6) == 13
    assert ratios.belt_lane_capacity("transport-belt") == pytest.approx(7.5)
    assert ratios.belt_lane_capacity("express-transport-belt") == pytest.approx(22.5)


@pytest.mark.parametrize("count", [1, 2, 3, 12])
def test_column_builds_and_round_trips(count):
    r = build({"type": "smelting_column", "count": count})
    kinds = [e.name for e in r.blueprint.entities]
    assert kinds.count("electric-furnace") == count
    assert kinds.count("fast-inserter") == 2 * count
    modules = math.ceil(count / 2)
    # per 2-furnace module: 6 ore belt, 5 plate belt (the splitter takes one row), 1 side-load belt
    assert kinds.count("transport-belt") == 12 * modules
    assert kinds.count("splitter") == modules
    again = Blueprint.from_string(r.string).to_string()
    assert again == r.string


def test_rate_spec_sizes_the_column():
    r = build({"type": "smelting_column", "rate": 7.5})
    assert [e.name for e in r.blueprint.entities].count("electric-furnace") == 12
    assert not any("WARNING" in n for n in r.notes)


def test_plate_belt_limit_is_the_full_belt():
    # lane balancing fills both lanes: 24 furnaces of iron is exactly a full yellow belt (15/s)
    assert not any("WARNING" in n for n in build({"type": "smelting_column", "count": 24}).notes)
    r = build({"type": "smelting_column", "count": 25})
    assert any("exceeds the transport-belt capacity (15.00/s)" in n for n in r.notes)


def test_full_red_belt_of_copper_needs_48_furnaces():
    r = build({"type": "smelting_column", "recipe": "copper-plate", "rate": 30, "belt": "fast-transport-belt"})
    kinds = [e.name for e in r.blueprint.entities]
    assert kinds.count("electric-furnace") == 48
    assert kinds.count("fast-splitter") == 24
    assert not any("WARNING" in n for n in r.notes)


def test_module_layout_balances_lanes():
    from draftsman.constants import Direction

    bp = build({"type": "smelting_column", "count": 2}).blueprint

    def at(x, y):
        return [e.name for e in bp.find_entities_filtered(position=(x + 0.5, y + 0.5))]

    assert at(1, 1) == at(5, 1) == ["medium-electric-pole"]
    assert at(1, 2) == at(1, 3) == at(5, 2) == at(5, 3) == ["fast-inserter"]
    (splitter,) = bp.find_entities_filtered(name="splitter")
    assert tuple(splitter.global_position) == (6.0, 4.5) and splitter.direction == Direction.SOUTH
    assert splitter.output_priority == "right"  # west output, opposite the inserters' drop lane
    (sideload,) = bp.find_entities_filtered(name="transport-belt", position=(5.5, 5.5))
    assert sideload.direction == Direction.EAST
    assert at(6, 5) == ["transport-belt"]


def test_odd_count_leaves_last_module_half_empty():
    bp = build({"type": "smelting_column", "count": 3}).blueprint
    assert len(bp.find_entities_filtered(name="electric-furnace")) == 3
    assert not bp.find_entities_filtered(position=(3.5, 10.5))  # where the 4th furnace would sit
    assert len(bp.find_entities_filtered(name="splitter")) == 2


def test_inserters_move_west_to_east():
    bp = build({"type": "smelting_column", "count": 2}).blueprint
    for ins in bp.find_entities_filtered(name="fast-inserter"):
        (px, _), (dx, _) = ins.pickup_position, ins.drop_position
        assert px < dx


def test_spec_errors():
    with pytest.raises(SpecError):
        build({"type": "smelting_column"})
    with pytest.raises(SpecError):
        build({"type": "smelting_column", "count": 2, "rate": 3})
    with pytest.raises(SpecError):
        build({"type": "smelting_column", "count": 2, "furnace": "steel-furnace"})
    with pytest.raises(SpecError):
        build({"type": "nope"})
    with pytest.raises(SpecError):
        build({"type": "smelting_column", "count": 1, "recipe": "not-a-recipe"})


@pytest.mark.parametrize(
    "bad",
    [
        {"rate": "7.5"},
        {"rate": True},
        {"rate": float("inf")},
        {"count": True},
        {"count": 2.0},
        {"count": 2, "belt": "iron-chest"},
        {"count": 2, "belt": ["transport-belt"]},
        {"count": 2, "inserter": "transport-belt"},
        {"count": 2, "pole": "iron-chest"},
        {"count": 2, "furnace": "assembling-machine-3"},
        {"count": 2, "recipe": ["iron-plate"]},
    ],
)
def test_malformed_spec_values_are_spec_errors(bad):
    with pytest.raises(SpecError):
        build({"type": "smelting_column", **bad})


def test_furnace_rejects_recipe_it_cannot_craft():
    with pytest.raises(SpecError, match="can't craft 'electronic-circuit'"):
        build({"type": "smelting_column", "count": 2, "recipe": "electronic-circuit"})
    with pytest.raises(SpecError, match="can't craft"):
        ratios.crafts_per_second("assembling-machine-1", "iron-plate")


def test_input_demand_counts_ingredient_amounts():
    assert ratios.ingredients_per_second("electric-furnace", "steel-plate") == {"iron-plate": pytest.approx(0.625)}
    assert ratios.ingredients_per_second("electric-furnace", "stone-brick") == {"stone": pytest.approx(1.25)}

    def demand_warnings(spec):
        return [n for n in build({"type": "smelting_column", **spec}).notes if "demand" in n]

    # steel: 5 iron plates per steel, so 3/s needs exactly one yellow belt (15/s) and 4/s needs 20/s
    assert demand_warnings({"recipe": "steel-plate", "rate": 3}) == []
    assert any("iron-plate demand 20.00/s" in n for n in demand_warnings({"recipe": "steel-plate", "rate": 4}))
    # stone brick: 2 stone per brick
    assert demand_warnings({"recipe": "stone-brick", "rate": 7.5}) == []
    assert demand_warnings({"recipe": "stone-brick", "rate": 8})


def test_checks_catch_missing_power_and_dangling_inserter():
    bp = Blueprint()
    bp.entities.append(new_entity("electric-furnace", tile_position=(2, 0)))
    bp.entities.append(new_entity("fast-inserter", tile_position=(10, 10)))
    assert any("not covered by any electric pole" in p for p in checks.power_coverage(bp))
    assert len(checks.inserter_wiring(bp)) == 2


@pytest.mark.parametrize(
    "pole, last",
    [("medium-electric-pole", 3), ("small-electric-pole", 2), ("big-electric-pole", 2)],
)
def test_power_reach_is_measured_from_the_pole_centre(pole, last):
    # The supply area spans supply_area_distance either side of the pole's centre: 7x7, 5x5, and only
    # 4x4 for the 2x2 big pole. With the pole at tile (0, 0), an inserter at tile x=`last` is the
    # furthest one east it powers.
    def covered(x):
        bp = Blueprint()
        bp.entities.append(new_entity(pole, tile_position=(0, 0)))
        bp.entities.append(new_entity("fast-inserter", tile_position=(x, 0)))
        return not checks.power_coverage(bp)

    assert covered(last)
    assert not covered(last + 1)


def test_pole_network_catches_unwired_and_overlong_wires():
    bp = Blueprint()
    bp.entities.append(new_entity("medium-electric-pole", tile_position=(0, 0)))
    bp.entities.append(new_entity("medium-electric-pole", tile_position=(0, 6)))
    assert any("not wired to the main pole network" in p for p in checks.pole_network(bp))
    bp.entities.append(new_entity("medium-electric-pole", tile_position=(0, 20)))
    with pytest.warns(Warning):  # draftsman warns on out-of-reach wires; the check must still fail it
        bp.add_power_connection(bp.entities[1], bp.entities[2])
    bp.add_power_connection(bp.entities[0], bp.entities[1])
    problems = checks.pole_network(bp)
    assert any("spans 14.00, reach is 9" in p for p in problems)
    assert not any("not wired" in p for p in problems)


@pytest.mark.parametrize("count", [1, 3, 12])
def test_column_poles_are_wired_as_a_ladder(count):
    bp = build({"type": "smelting_column", "count": count}).blueprint
    pairs = len(bp.find_entities_filtered(type="electric-pole")) // 2
    # one rung across each pair, plus a run down each side between pairs
    assert len(bp.wires) == pairs + 2 * (pairs - 1)
    assert checks.pole_network(bp) == []


def test_unwired_blueprint_string_is_rejected():
    bp = build({"type": "smelting_column", "count": 4}).blueprint
    bp.remove_power_connections()
    assert any("not wired" in p for p in checks.pole_network(bp))


def test_warnings_become_build_errors(monkeypatch):
    from blueprint_smith import generators

    def overlapping(spec):
        return [new_entity("electric-furnace", tile_position=(0, 0)), new_entity("electric-furnace", tile_position=(1, 1))], []

    monkeypatch.setitem(generators.REGISTRY, "overlap", overlapping)
    with pytest.raises(BuildError) as ei:
        build({"type": "overlap"})
    assert any("OverlappingObjectsWarning" in p for p in ei.value.problems)


def _mutated(monkeypatch, mutate):
    from blueprint_smith import generators

    orig = generators.REGISTRY["smelting_column"]

    def wrapper(spec):
        entities, notes = orig(spec)
        mutate(entities)
        return entities, notes

    monkeypatch.setitem(generators.REGISTRY, "smelting_column", wrapper)


def test_reversed_inserters_are_rejected(monkeypatch):
    from draftsman.constants import Direction

    def flip(entities):
        for e in entities:
            if e.name == "fast-inserter":
                e.direction = Direction.EAST

    _mutated(monkeypatch, flip)
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any("moves the wrong way" in p for p in ei.value.problems)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda e: setattr(e, "direction", 0) if e.name == "splitter" else None, "must face south across cols"),
        (lambda e: setattr(e, "output_priority", "none") if e.name == "splitter" else None, "must prioritise its west output"),
        (lambda e: setattr(e, "output_priority", "left") if e.name == "splitter" else None, "must prioritise its west output"),
        (lambda e: setattr(e, "direction", 8) if e.name == "transport-belt" and e.global_position[0] == 5.5 else None,
         "must face east under a splitter"),
    ],
)
def test_broken_lane_balancing_is_rejected(monkeypatch, mutate, message):
    _mutated(monkeypatch, lambda entities: [mutate(e) for e in entities])
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any(message in p for p in ei.value.problems)


def test_missing_sideload_belt_is_rejected(monkeypatch):
    def drop_sideload(entities):
        entities[:] = [e for e in entities if not (e.name == "transport-belt" and e.global_position[0] == 5.5)]

    _mutated(monkeypatch, drop_sideload)
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any("no side-load belt under its west output" in p for p in ei.value.problems)


def test_missing_poles_are_rejected(monkeypatch):
    _mutated(monkeypatch, lambda entities: entities.__setitem__(slice(None), [e for e in entities if "pole" not in e.name]))
    with pytest.raises(BuildError) as ei:
        build({"type": "smelting_column", "count": 2})
    assert any("not covered by any electric pole" in p for p in ei.value.problems)


def test_cli_build_then_decode(tmp_path, capsys):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"type": "smelting_column", "count": 2, "label": "iron"}))
    out = tmp_path / "bp.txt"
    assert main(["build", str(spec), "-o", str(out)]) == 0
    decoded = string_to_JSON(out.read_text().strip())
    assert decoded["blueprint"]["label"] == "iron"
    assert main(["decode", f"@{out}"]) == 0
    assert '"electric-furnace"' in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "smelting_column"}))
    assert main(["build", str(bad)]) == 2


def test_cli_bad_spec_input_exits_2(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text('{"type": ')
    assert main(["build", str(broken)]) == 2
    assert main(["build", str(tmp_path / "missing.json")]) == 2
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"type": "smelting_column", "rate": "7.5"}))
    assert main(["build", str(wrong)]) == 2
    assert capsys.readouterr().err.count("spec error:") == 3
