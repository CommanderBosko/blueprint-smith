"""M2 checks: modules, beacon reach, underground pairing, hidden entities. The geometry and module rules here
were confirmed on the 2.0.77 headless server (blueprints pasted and revived, then `get_beacon_effect_receivers`,
underground `neighbours` and `can_insert` on module inventories)."""
import pytest
from draftsman.blueprintable import Blueprint
from draftsman.constants import Direction
from draftsman.entity import new_entity

from blueprint_smith import checks, generators
from blueprint_smith.errors import BuildError
from blueprint_smith.pipeline import build

L = "legendary"
E, W, N = Direction.EAST, Direction.WEST, Direction.NORTH


def _bp(*entities):
    bp = Blueprint()
    for e in entities:
        bp.entities.append(e)
    return bp


def _machine(name="electromagnetic-plant", at=(0, 0), module="productivity-module-3", n=5, recipe="electronic-circuit", quality=L):
    e = new_entity(name, tile_position=at, quality=quality, **({"recipe": recipe} if recipe else {}))
    if n:
        e.request_modules(module, range(n), quality=quality)
    return e


def _beacon(at, module="speed-module-3", quality=L):
    e = new_entity("beacon", tile_position=at, quality=quality)
    if module:
        e.request_modules(module, (0, 1), quality=quality)
    return e


# --- end to end: one legendary plant between two legendary beacons, through pipeline.build ---


def _cell(plant=None, east=(4, 0), extra=()):
    """A 4x4 plant at tiles 0-3, beacons west (tiles -3..-1) and east, and a substation powering all of it."""
    return [
        plant or _machine(),
        _beacon((-3, 0)),
        _beacon(east),
        new_entity("substation", tile_position=(4, 3)),
        *extra,
    ]


def _register(monkeypatch, entities):
    monkeypatch.setitem(generators.REGISTRY, "m2_cell", lambda spec: (entities, [], []))


def test_beaconed_plant_builds_clean(monkeypatch):
    _register(monkeypatch, _cell())
    bp = build({"type": "m2_cell"}).blueprint
    plant, west, east, _ = bp.entities
    assert checks.beacon_targets(bp) == {plant: [west, east]}
    assert checks.module_items(plant) == [("productivity-module-3", L)] * 5
    assert checks.module_items(east) == [("speed-module-3", L)] * 2
    assert east.quality == L


def _ug_entrance(entities):
    return [*entities, new_entity("turbo-underground-belt", tile_position=(0, 6), direction=E, io_type="input")]


@pytest.mark.parametrize(
    "entities, message",
    [
        (_cell(extra=[]), None),
        (_cell(plant=_machine(n=6)), "electromagnetic-plant at (2.0, 2.0) requests 6 modules into 5 module slots"),
        ([_machine(), _beacon((-3, 0), module="productivity-module-3"), new_entity("substation", tile_position=(4, 3))],
         "beacon at (-1.5, 1.5) can't take productivity-module-3: productivity not allowed"),
        (_cell(east=(7, 0)), "beacon at (8.5, 1.5) reaches no machine that takes beacon effects"),
        (_ug_entrance(_cell()), "turbo-underground-belt entrance at (0.5, 6.5) has no exit within 11 tiles"),
        (_cell(extra=[new_entity("turbo-loader", tile_position=(0, 6))]), "turbo-loader at (0.5, 7.0) is hidden"),
    ],
    ids=["clean", "6-modules-in-plant", "prod-in-beacon", "beacon-out-of-reach", "unpaired-underground", "turbo-loader"],
)
def test_mutations_fail_the_build(monkeypatch, entities, message):
    _register(monkeypatch, entities)
    if message is None:
        build({"type": "m2_cell"})
        return
    with pytest.raises(BuildError) as ei:
        build({"type": "m2_cell"})
    assert any(message in p for p in ei.value.problems), ei.value.problems


# --- module_validity ---


@pytest.mark.parametrize(
    "entity",
    [
        _machine(),
        _beacon((0, 0)),
        _beacon((0, 0), module="efficiency-module-3"),  # efficiency only lowers consumption: allowed in beacons
        # speed modules carry -quality; 2.0 only restricts bonuses, so drills, pumpjacks and refineries take them
        _machine("electric-mining-drill", module="speed-module-3", n=3, recipe=None, quality="normal"),
        _machine("pumpjack", module="speed-module-3", n=2, recipe=None, quality="normal"),
        _machine("oil-refinery", module="speed-module-3", n=3, recipe="advanced-oil-processing", quality="normal"),
        _machine("chemical-plant", module="speed-module-3", n=3, recipe="lubricant", quality="normal"),
        _machine("assembling-machine-3", n=4, recipe=None, quality="normal"),
        _machine("electric-furnace", n=2, recipe=None, quality="normal"),
        _machine("electric-mining-drill", module="quality-module-3", n=3, recipe=None, quality="normal"),
        _machine("lab", module="productivity-module-3", n=2, recipe=None, quality="normal"),
        _machine("recycler", module="quality-module-3", n=4, recipe=None, quality="normal"),
        new_entity("electromagnetic-plant", tile_position=(0, 0), recipe="electronic-circuit"),  # no modules at all
    ],
    ids=lambda e: f"{e.name}-{(checks.module_items(e) or [('none',)])[0][0]}",
)
def test_valid_modules_pass(entity):
    assert checks.module_validity(_bp(entity)) == []


@pytest.mark.parametrize(
    "entity, message",
    [
        (_beacon((0, 0), module="productivity-module-3"), "can't take productivity-module-3: productivity not allowed"),
        (_beacon((0, 0), module="quality-module-3"), "can't take quality-module-3: quality not allowed"),
        (_machine(n=6), "requests 6 modules into 5 module slots"),
        (_machine("assembling-machine-3", n=4, recipe="iron-chest", quality="normal"),
         "can't take productivity-module-3 with recipe iron-chest: productivity not allowed"),
        (_machine("chemical-plant", module="quality-module-3", n=3, recipe="lubricant", quality="normal"),
         "can't take quality-module-3 with recipe lubricant: quality not allowed"),
        (_machine("recycler", n=4, recipe=None, quality="normal"), "can't take productivity-module-3: productivity not allowed"),
        (_machine("pumpjack", module="quality-module-3", n=2, recipe=None, quality="normal"), "quality not allowed"),
        (_machine("lab", module="quality-module-3", n=2, recipe=None, quality="normal"), "quality not allowed"),
    ],
    ids=["prod-in-beacon", "quality-in-beacon", "6-in-plant", "prod-for-iron-chest", "quality-for-lubricant",
         "prod-in-recycler", "quality-in-pumpjack", "quality-in-lab"],
)
def test_invalid_modules_are_rejected(entity, message):
    problems = checks.module_validity(_bp(entity))
    assert any(message in p for p in problems), problems


def test_module_categories_are_enforced_when_given(monkeypatch):
    # no 2.0.77 prototype sets allowed_module_categories; a mod could, on the entity or the recipe
    from draftsman.data import entities, recipes

    monkeypatch.setitem(entities.raw, "beacon", {**entities.raw["beacon"], "allowed_module_categories": ["efficiency"]})
    recipe = {**recipes.raw["electronic-circuit"], "allowed_module_categories": ["productivity"]}
    monkeypatch.setitem(recipes.raw, "electronic-circuit", recipe)
    assert checks.module_validity(_bp(_beacon((0, 0)), _machine(at=(3, 0)))) == [
        "beacon at (1.5, 1.5) can't take speed-module-3: category speed not allowed"
    ]
    assert checks.module_validity(_bp(_machine(module="speed-module-3"))) == [
        "electromagnetic-plant at (2.0, 2.0) can't take speed-module-3 with recipe electronic-circuit: "
        "category speed not allowed"
    ]


def test_legendary_quality_adds_no_module_slots():
    # a legendary plant still has 5 slots in 2.0.77 (inserting 6 legendary modules in-game stops at 5)
    problems = checks.module_validity(_bp(_machine(n=6, quality=L)))
    assert problems == ["electromagnetic-plant at (2.0, 2.0) requests 6 modules into 5 module slots"]


def test_non_modules_and_bad_slots_are_rejected():
    beacon = new_entity("beacon", tile_position=(0, 0))
    beacon.set_item_request("iron-plate", 1, inventory=1, slot=0)
    assert checks.module_validity(_bp(beacon)) == [
        "beacon at (1.5, 1.5) requests iron-plate into its module slots, but it isn't a module"
    ]
    plant = new_entity("electromagnetic-plant", tile_position=(0, 0))
    plant.request_modules("speed-module-3", (0, 7))
    assert checks.module_validity(_bp(plant)) == [
        "electromagnetic-plant at (2.0, 2.0) requests module slot 7, but its slots are 0-4"
    ]
    # ingredients requested into the plant's input inventory aren't modules and aren't judged here
    plant = new_entity("electromagnetic-plant", tile_position=(0, 0), recipe="electronic-circuit")
    plant.set_item_request("iron-plate", 10, inventory=2)
    assert checks.module_validity(_bp(plant)) == []


# --- beacon_targets / beacon_reach ---

# beacon at tiles 0-2 (reach 3: tiles -3..5); a machine at `at` is reached iff one of its tiles is in that square
REACH_CASES = [
    ("assembling-machine-3", (5, 0), True),
    ("assembling-machine-3", (6, 0), False),
    ("assembling-machine-3", (-5, 0), True),
    ("assembling-machine-3", (-6, 0), False),
    ("assembling-machine-3", (5, 5), True),  # the area is a square: corners count
    ("assembling-machine-3", (6, 5), False),
    ("electromagnetic-plant", (5, 0), True),
    ("electromagnetic-plant", (6, 0), False),
    ("electromagnetic-plant", (-6, 0), True),
    ("electromagnetic-plant", (-7, 0), False),
    ("electromagnetic-plant", (5, 5), True),
    ("lab", (5, 0), True),
    ("lab", (6, 5), False),
    ("recycler", (5, 0), True),  # 2x4, collision box inset 0.3 like the others
    ("recycler", (6, 0), False),
    ("electric-mining-drill", (5, 0), True),  # collision inset only 0.15
    ("electric-mining-drill", (6, 0), False),
    ("assembling-machine-1", (3, 0), False),  # effect_receiver.uses_beacon_effects = false
    ("stone-furnace", (3, 0), False),
    ("burner-mining-drill", (3, 0), False),  # allowed_effects = {}
]


@pytest.mark.parametrize("name, at, reached", REACH_CASES, ids=lambda v: str(v))
@pytest.mark.parametrize("quality", ["normal", L])  # quality doesn't change the reach in 2.0.77
def test_beacon_reach_matches_the_game(name, at, reached, quality):
    beacon = _beacon((0, 0), quality=quality)
    machine = new_entity(name, tile_position=at)
    bp = _bp(beacon, machine)
    targets = checks.beacon_targets(bp)
    if name in ("assembling-machine-1", "stone-furnace", "burner-mining-drill"):
        assert targets == {}
    else:
        assert targets == {bp.entities[1]: [bp.entities[0]] if reached else []}
    assert (checks.beacon_reach(bp) == []) == reached


def test_beacon_targets_lists_every_machine_and_beacon_in_order():
    bp = _bp(
        _machine(at=(0, 0)),
        _machine(at=(9, 0)),
        _machine(at=(19, 0)),
        _beacon((4, 0)),  # gap 0 to the first plant, 2 to the second: reaches both
        _beacon((14, 4)),  # below and between the second and third: reaches both
        _beacon((13, 0)),  # next to the second; gap 3 to the third
    )
    p1, p2, p3, b1, b2, b3 = bp.entities
    assert checks.beacon_targets(bp) == {p1: [b1], p2: [b1, b2, b3], p3: [b2]}
    assert checks.beacon_reach(bp) == []


def test_lone_beacon_is_rejected():
    bp = _bp(_beacon((0, 0)), new_entity("assembling-machine-1", tile_position=(3, 0)))
    assert checks.beacon_reach(bp) == ["beacon at (1.5, 1.5) reaches no machine that takes beacon effects"]


# --- underground_pairing ---


def _ug(x, d=E, io="input", name="underground-belt", y=0):
    return new_entity(name, tile_position=(x, y), direction=d, io_type=io)


@pytest.mark.parametrize(
    "entities",
    [
        [_ug(0), _ug(5, io="output")],  # yellow: max_distance 5, entrance to exit
        [_ug(0, name="fast-underground-belt"), _ug(7, io="output", name="fast-underground-belt")],
        [_ug(0, name="express-underground-belt"), _ug(9, io="output", name="express-underground-belt")],
        [_ug(0, name="turbo-underground-belt"), _ug(11, io="output", name="turbo-underground-belt")],
        [_ug(0, N, y=5), _ug(0, N, "output", y=1)],
        # other tiers and perpendicular undergrounds are passed under
        [_ug(0), _ug(1, name="fast-underground-belt"), _ug(3, io="output", name="fast-underground-belt"), _ug(4, io="output")],
        [_ug(0), _ug(2, N, y=0), _ug(2, N, "output", y=-2), _ug(4, io="output")],
        # two pairs in a row
        [_ug(0), _ug(2, io="output"), _ug(3), _ug(5, io="output")],
    ],
    ids=["yellow-5", "red-7", "blue-9", "turbo-11", "north", "weave-tiers", "perpendicular", "two-pairs"],
)
def test_paired_undergrounds_pass(entities):
    assert checks.underground_pairing(_bp(*entities)) == []


@pytest.mark.parametrize(
    "entities, problems",
    [
        ([_ug(0), _ug(6, io="output")], [
            "underground-belt entrance at (0.5, 0.5) has no exit within 5 tiles",
            "underground-belt exit at (6.5, 0.5) has no entrance within 5 tiles",
        ]),
        ([_ug(0, name="turbo-underground-belt"), _ug(12, io="output", name="turbo-underground-belt")], [
            "turbo-underground-belt entrance at (0.5, 0.5) has no exit within 11 tiles",
            "turbo-underground-belt exit at (12.5, 0.5) has no entrance within 11 tiles",
        ]),
        # the game pairs the nearer entrance; the far one is left unpaired
        ([_ug(0), _ug(2), _ug(4, io="output")], [
            "underground-belt entrance at (0.5, 0.5) is blocked by the entrance facing 4 at (2.5, 0.5)",
        ]),
        ([_ug(0), _ug(2, io="output"), _ug(4, io="output")], [
            "underground-belt exit at (4.5, 0.5) is blocked by the exit facing 4 at (2.5, 0.5)",
        ]),
        # a same-tier pair facing back, in between, cuts the east pair (in-game: both ends unpaired)
        ([_ug(0), _ug(2, W, "output"), _ug(3, W), _ug(4, io="output")], [
            "underground-belt entrance at (0.5, 0.5) is blocked by the exit facing 12 at (2.5, 0.5)",
            "underground-belt exit at (4.5, 0.5) is blocked by the entrance facing 12 at (3.5, 0.5)",
        ]),
        ([_ug(0), _ug(4, W, "output")], [
            "underground-belt entrance at (0.5, 0.5) is blocked by the exit facing 12 at (4.5, 0.5)",
            "underground-belt exit at (4.5, 0.5) has no entrance within 5 tiles",
        ]),
        ([_ug(0), _ug(3, io="output", y=1)], [
            "underground-belt entrance at (0.5, 0.5) has no exit within 5 tiles",
            "underground-belt exit at (3.5, 1.5) has no entrance within 5 tiles",
        ]),
        ([_ug(0, io="output"), _ug(4)], [
            "underground-belt exit at (0.5, 0.5) has no entrance within 5 tiles",
            "underground-belt entrance at (4.5, 0.5) has no exit within 5 tiles",
        ]),
        ([_ug(0), _ug(2, io="output", name="fast-underground-belt")], [
            "underground-belt entrance at (0.5, 0.5) has no exit within 5 tiles",
            "fast-underground-belt exit at (2.5, 0.5) has no entrance within 7 tiles",
        ]),
    ],
    ids=["yellow-6", "turbo-12", "entrance-entrance-exit", "entrance-exit-exit", "reversed-pair-between",
         "exit-faces-back", "off-line", "exit-before-entrance", "different-tier"],
)
def test_unpaired_undergrounds_are_rejected(entities, problems):
    assert checks.underground_pairing(_bp(*entities)) == problems


# --- hidden_entities ---


@pytest.mark.parametrize(
    "name",
    ["turbo-loader", "express-loader", "infinity-chest", "infinity-pipe", "linked-belt",
     "electric-energy-interface", "bottomless-chest", "burner-generator"],
)
def test_hidden_entities_are_rejected(name):
    bp = _bp(new_entity(name, tile_position=(0, 0)))
    (problem,) = checks.hidden_entities(bp)
    assert problem.startswith(f"{name} at ") and problem.endswith("is hidden: no item a player can get places it")


@pytest.mark.parametrize(
    "name",
    ["electric-furnace", "fast-inserter", "transport-belt", "fast-transport-belt", "express-transport-belt",
     "splitter", "fast-splitter", "express-splitter", "medium-electric-pole", "electromagnetic-plant", "beacon",
     "stack-inserter", "bulk-inserter", "turbo-transport-belt", "turbo-underground-belt", "turbo-splitter",
     "substation", "iron-chest", "straight-rail"],
)
def test_buildable_entities_pass(name):
    assert checks.hidden_entities(_bp(new_entity(name, tile_position=(0, 0)))) == []
