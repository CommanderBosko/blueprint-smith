"""Smelting column: ore belt | inserter | furnace | inserter | plate belt, repeated top to bottom.

Columns (tile x): 0 ore belt, 1 input inserter, 2-4 furnace, 5 output inserter, 6 plate belt.
Both belts flow south. An inserter's blueprint `direction` is the side it PICKS UP from
(verified against prototype pickup/drop positions), so both inserters use WEST.
"""
import math

from draftsman.constants import Direction
from draftsman.data import entities
from draftsman.entity import new_entity

from .. import ratios
from ..errors import SpecError
from . import register

ORE_X, IN_X, FURNACE_X, OUT_X, PLATE_X = 0, 1, 2, 5, 6
FURNACE_SIZE = 3


def _furnace_tiles(furnace: str) -> int:
    try:
        box = entities.raw[furnace]["collision_box"]
    except KeyError:
        raise SpecError(f"unknown furnace {furnace!r}") from None
    return round(box[1][0] - box[0][0] + 0.2)


def check_flow(bp) -> list[str]:
    """Input inserters must move ore belt -> furnace; output inserters furnace -> plate belt."""
    problems = []
    furnace_cols = range(FURNACE_X, FURNACE_X + FURNACE_SIZE)
    for e in bp.entities:
        if e.prototype.get("type") == "inserter":
            px, dx = math.floor(e.pickup_position[0]), math.floor(e.drop_position[0])
            col = math.floor(e.global_position[0])
            ok = (col == IN_X and px == ORE_X and dx in furnace_cols) or (
                col == OUT_X and px in furnace_cols and dx == PLATE_X
            )
            if not ok:
                problems.append(f"{e.name} at {tuple(e.global_position)} moves the wrong way (pickup x={px}, drop x={dx})")
        elif e.prototype.get("type") == "transport-belt" and e.direction != Direction.SOUTH:
            problems.append(f"{e.name} at {tuple(e.global_position)} must flow south")
    return problems


@register("smelting_column", checks=(check_flow,))
def smelting_column(spec: dict) -> tuple[list, list[str]]:
    furnace = spec.get("furnace", "electric-furnace")
    recipe = spec.get("recipe", "iron-plate")
    belt = spec.get("belt", "transport-belt")
    inserter = spec.get("inserter", "fast-inserter")
    pole = spec.get("pole", "medium-electric-pole")

    if _furnace_tiles(furnace) != FURNACE_SIZE:
        raise SpecError(f"smelting_column only supports 3x3 furnaces (electric-furnace), got {furnace!r}")
    if ("count" in spec) == ("rate" in spec):
        raise SpecError("smelting_column needs exactly one of 'count' or 'rate' (plates per second)")

    per_furnace = ratios.crafts_per_second(furnace, recipe)
    if "count" in spec:
        n = spec["count"]
        if not isinstance(n, int) or n < 1:
            raise SpecError("'count' must be a positive integer")
    else:
        if not spec["rate"] > 0:
            raise SpecError("'rate' must be positive")
        n = ratios.machines_for_rate(furnace, recipe, spec["rate"])

    out: list = []
    rows = n * FURNACE_SIZE
    for y in range(rows):
        out.append(new_entity(belt, tile_position=(ORE_X, y), direction=Direction.SOUTH))
        out.append(new_entity(belt, tile_position=(PLATE_X, y), direction=Direction.SOUTH))
    for i in range(n):
        y0 = i * FURNACE_SIZE
        out.append(new_entity(furnace, tile_position=(FURNACE_X, y0)))
        out.append(new_entity(inserter, tile_position=(IN_X, y0 + 1), direction=Direction.WEST))
        out.append(new_entity(inserter, tile_position=(OUT_X, y0 + 1), direction=Direction.WEST))
        # One pole (both columns) per pair of furnaces; a medium pole's 7x7 area spans two 3-tile rows.
        if i % 2 == 1:
            out.append(new_entity(pole, tile_position=(IN_X, y0)))
            out.append(new_entity(pole, tile_position=(OUT_X, y0)))
        elif i == n - 1:
            out.append(new_entity(pole, tile_position=(IN_X, y0 + 2)))
            out.append(new_entity(pole, tile_position=(OUT_X, y0 + 2)))

    total = n * per_furnace
    notes = [f"{n} x {furnace}: {total:.3f} {recipe}/s ({per_furnace:.3f}/s each, base crafting speed, no modules)"]
    lane = ratios.belt_lane_capacity(belt)
    if total > lane + 1e-9:
        notes.append(
            f"WARNING: output {total:.2f}/s exceeds one {belt} lane ({lane:.2f}/s) — inserters fill only the far lane, "
            f"so the plate belt will back up; use a faster belt or fewer furnaces (max ~{int(lane / per_furnace)})"
        )
    if total > 2 * lane + 1e-9:
        notes.append(f"WARNING: ore demand {total:.2f}/s exceeds the ore {belt} capacity ({2 * lane:.2f}/s)")
    return out, notes
