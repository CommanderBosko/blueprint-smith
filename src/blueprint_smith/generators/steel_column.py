"""Steel column: ore belt | inserter | iron furnace | inserter | steel furnace | inserter | steel belt.

Columns (tile x): 0 ore belt, 1 inserter, 2-4 iron furnace, 5 inserter, 6-8 steel furnace, 9 inserter,
10 steel belt. Both belts flow south, and every inserter picks up from the WEST (its blueprint `direction`).

Direct insertion (technique T4): a furnace makes 0.625 iron plates/s and a steel furnace eats exactly
0.625 plates/s (5 plates per 16 s recipe vs 1 per 3.2 s, at the same crafting speed), so each iron
furnace hands its plates straight to the steel furnace beside it, with no belt in between. Furnaces
pick their recipe from what they're fed: ore makes plates, plates make steel.

Same 6-row module as the smelting column (paired inserters, T2), with a pole on row 1 of each of the
3 inserter columns: a medium pole reaches 3 tiles each way, so no single pole covers cols 1 and 5, or 5 and 9.
No lane balancing (T1) on the steel belt: steel is a fifth of the ore input, so it can never fill
even the one lane the output inserters drop onto.
"""
import math

from draftsman.constants import Direction
from draftsman.entity import new_entity

from .. import ratios
from ..errors import SpecError
from . import register
from .columns import FURNACE_SIZE, MODULE_ROWS, POLE_ROW, column_furnace, entity_option, machine_count, modules

ORE_X, IN_X, IRON_X, MID_X, STEEL_X, OUT_X, STEEL_BELT_X = 0, 1, 2, 5, 6, 9, 10
IRON_COLS = set(range(IRON_X, IRON_X + FURNACE_SIZE))
STEEL_COLS = set(range(STEEL_X, STEEL_X + FURNACE_SIZE))
# inserter column -> (columns it may pick up from, columns it may drop onto)
FLOW = {
    IN_X: ({ORE_X}, IRON_COLS),
    MID_X: (IRON_COLS, STEEL_COLS),
    OUT_X: (STEEL_COLS, {STEEL_BELT_X}),
}


def check_flow(bp) -> list[str]:
    """Inserters move ore belt -> iron furnace -> steel furnace -> steel belt; both belts flow south;
    every iron furnace has a steel furnace beside it, and every furnace has an inserter loading it and one unloading it."""
    problems = []
    furnaces = {}  # id -> (entity, loaders, unloaders)
    rows = {IRON_X: set(), STEEL_X: set()}
    for e in bp.entities:
        if e.prototype.get("type") == "furnace":
            left, top = math.floor(e.global_position[0]) - 1, math.floor(e.global_position[1]) - 1
            if left not in rows:
                problems.append(f"{e.name} at {tuple(e.global_position)} must sit in cols {IRON_X}-{IRON_X + 2} or {STEEL_X}-{STEEL_X + 2}")
            else:
                rows[left].add(top)
            furnaces[id(e)] = [e, 0, 0]
    for e in bp.entities:
        kind = e.prototype.get("type")
        col = math.floor(e.global_position[0])
        if kind == "inserter":
            px, dx = math.floor(e.pickup_position[0]), math.floor(e.drop_position[0])
            pick, drop = FLOW.get(col, (set(), set()))
            if px not in pick or dx not in drop:
                problems.append(f"{e.name} at {tuple(e.global_position)} moves the wrong way (pickup x={px}, drop x={dx})")
            for pos, slot in ((e.drop_position, 1), (e.pickup_position, 2)):
                for f in bp.find_entities_filtered(position=tuple(pos), type="furnace"):
                    furnaces[id(f)][slot] += 1
        elif kind == "transport-belt" and (col not in (ORE_X, STEEL_BELT_X) or e.direction != Direction.SOUTH):
            problems.append(f"{e.name} at {tuple(e.global_position)} must flow south in col {ORE_X} or {STEEL_BELT_X}")
    for top in rows[IRON_X] ^ rows[STEEL_X]:
        problems.append(f"the furnace at row {top} has no partner: every iron furnace needs a steel furnace beside it")
    for f, loaders, unloaders in furnaces.values():
        if not loaders or not unloaders:
            problems.append(f"{f.name} at {tuple(f.global_position)} needs an inserter loading it and one unloading it")
    return problems


@register("steel_column", checks=(check_flow,))
def steel_column(spec: dict) -> tuple[list, list[str]]:
    furnace = column_furnace(spec, "steel_column")
    belt = entity_option(spec, "belt", "transport-belt", "transport-belt")
    inserter = entity_option(spec, "inserter", "fast-inserter", "inserter")
    pole = entity_option(spec, "pole", "medium-electric-pole", "electric-pole")

    plates = ratios.crafts_per_second(furnace, "iron-plate")
    plate_demand = ratios.ingredients_per_second(furnace, "steel-plate")["iron-plate"]
    if not math.isclose(plates, plate_demand):
        raise SpecError(
            f"steel_column pairs one iron furnace with one steel furnace, which needs them to match: "
            f"{furnace} makes {plates:.3f} iron plates/s but a steel furnace eats {plate_demand:.3f}/s"
        )
    n = machine_count(spec, "steel_column", furnace, "steel-plate", "steel plates")

    out: list = []
    for y0, slots in modules(n):
        for dy in range(MODULE_ROWS):
            out.append(new_entity(belt, tile_position=(ORE_X, y0 + dy), direction=Direction.SOUTH))
            out.append(new_entity(belt, tile_position=(STEEL_BELT_X, y0 + dy), direction=Direction.SOUTH))
        for x in FLOW:
            out.append(new_entity(pole, tile_position=(x, y0 + POLE_ROW)))
        for top, row in slots:
            out.append(new_entity(furnace, tile_position=(IRON_X, top)))
            out.append(new_entity(furnace, tile_position=(STEEL_X, top)))
            for x in FLOW:
                out.append(new_entity(inserter, tile_position=(x, row), direction=Direction.WEST))

    steel = n * ratios.crafts_per_second(furnace, "steel-plate")
    ore = n * ratios.ingredients_per_second(furnace, "iron-plate")["iron-ore"]
    notes = [
        f"{n} x {furnace} (iron plate) feeding {n} x {furnace} (steel): {steel:.3f} steel-plate/s from {ore:.3f} iron-ore/s "
        f"({plates:.3f} plates/s through each pair, base crafting speed, no modules)"
    ]
    full = 2 * ratios.belt_lane_capacity(belt)
    if ore > full + 1e-9:
        notes.append(
            f"WARNING: iron-ore demand {ore:.2f}/s exceeds the input {belt} capacity ({full:.2f}/s); "
            f"use a faster belt or fewer pairs (max ~{int(full / plates)})"
        )
    return out, notes
