"""Smelting column: ore belt | inserter | furnace | inserter | plate belt, repeated top to bottom.

Columns (tile x): 0 ore belt, 1 input inserter, 2-4 furnace, 5 output inserter, 6 plate belt.
Both belts flow south. An inserter's blueprint `direction` is the side it PICKS UP from
(verified against prototype pickup/drop positions), so both inserters use WEST.

The column repeats every two furnaces (A on top, B below; 6 rows). Relative rows:
  1: poles in cols 1 and 5            2-3: inserters (A's bottom row, B's top row)
  4: south-facing splitter, cols 5-6  5: east-facing belt in col 5
Output inserters only fill the plate belt's far (east) lane. Each splitter has output priority on
its west side, so plates go out west first, turn east and side-load onto the near (west) lane;
only once that lane is full do they continue east. The far lane, where the inserters drop, stays
as empty as possible, and both lanes end up full.
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
MODULE_ROWS = 2 * FURNACE_SIZE
POLE_ROW, SPLITTER_ROW, SIDELOAD_ROW = 1, 4, 5
# A splitter's left/right are relative to its facing: facing south, "right" is the west output.
SPLITTER_PRIORITY = "right"


def _entity(spec: dict, key: str, default: str, kind: str) -> str:
    """spec[key] (or `default`) must name an entity whose prototype type is `kind`."""
    name = spec.get(key, default)
    if not isinstance(name, str) or entities.raw.get(name, {}).get("type") != kind:
        raise SpecError(f"'{key}' must name a {kind} entity, got {name!r}")
    return name


def _furnace_tiles(furnace: str) -> int:
    box = entities.raw[furnace]["collision_box"]
    return round(box[1][0] - box[0][0] + 0.2)


def _splitter_for(belt: str) -> str:
    """The splitter that runs at the same speed as `belt`."""
    speed = entities.raw[belt]["speed"]
    for name, proto in entities.raw.items():
        if proto.get("type") == "splitter" and proto.get("speed") == speed:
            return name
    raise SpecError(f"no splitter matches the speed of {belt!r}")


def check_flow(bp) -> list[str]:
    """Inserters move ore belt -> furnace -> plate belt; ore and plate belts flow south;
    every splitter faces south across cols 5-6, prioritises its west output, and that output side-loads
    east onto the plate belt."""
    problems = []
    furnace_cols = range(FURNACE_X, FURNACE_X + FURNACE_SIZE)
    belts = {}
    splitter_rows = set()
    for e in bp.entities:
        kind = e.prototype.get("type")
        col, row = math.floor(e.global_position[0]), math.floor(e.global_position[1])
        if kind == "inserter":
            px, dx = math.floor(e.pickup_position[0]), math.floor(e.drop_position[0])
            ok = (col == IN_X and px == ORE_X and dx in furnace_cols) or (
                col == OUT_X and px in furnace_cols and dx == PLATE_X
            )
            if not ok:
                problems.append(f"{e.name} at {tuple(e.global_position)} moves the wrong way (pickup x={px}, drop x={dx})")
        elif kind == "transport-belt":
            belts[(col, row)] = e
            if col != OUT_X and e.direction != Direction.SOUTH:
                problems.append(f"{e.name} at {tuple(e.global_position)} must flow south")
        elif kind == "splitter":
            # a south-facing 2x1 splitter over cols 5-6 is centred on x=6
            if e.direction != Direction.SOUTH or e.global_position[0] != PLATE_X:
                problems.append(f"{e.name} at {tuple(e.global_position)} must face south across cols {OUT_X}-{PLATE_X}")
            if e.output_priority != SPLITTER_PRIORITY:
                problems.append(
                    f"{e.name} at {tuple(e.global_position)} must prioritise its west output "
                    f"(output_priority={SPLITTER_PRIORITY!r}), got {e.output_priority!r}"
                )
            splitter_rows.add(row)
    for (col, row), e in belts.items():
        if col == OUT_X and (e.direction != Direction.EAST or row - 1 not in splitter_rows):
            problems.append(f"{e.name} at {tuple(e.global_position)} must face east under a splitter to side-load the plate belt")
    for row in splitter_rows:
        if (OUT_X, row + 1) not in belts:
            problems.append(f"splitter at row {row} has no side-load belt under its west output")
    return problems


@register("smelting_column", checks=(check_flow,))
def smelting_column(spec: dict) -> tuple[list, list[str]]:
    furnace = _entity(spec, "furnace", "electric-furnace", "furnace")
    recipe = spec.get("recipe", "iron-plate")
    belt = _entity(spec, "belt", "transport-belt", "transport-belt")
    inserter = _entity(spec, "inserter", "fast-inserter", "inserter")
    pole = _entity(spec, "pole", "medium-electric-pole", "electric-pole")
    splitter = _splitter_for(belt)

    if _furnace_tiles(furnace) != FURNACE_SIZE:
        raise SpecError(f"smelting_column only supports 3x3 furnaces (electric-furnace), got {furnace!r}")
    if ("count" in spec) == ("rate" in spec):
        raise SpecError("smelting_column needs exactly one of 'count' or 'rate' (plates per second)")

    per_furnace = ratios.crafts_per_second(furnace, recipe)
    if "count" in spec:
        n = spec["count"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise SpecError("'count' must be a positive integer")
    else:
        rate = spec["rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise SpecError("'rate' must be a positive number (plates per second)")
        n = ratios.machines_for_rate(furnace, recipe, rate)

    out: list = []
    for m in range(math.ceil(n / 2)):
        y0 = m * MODULE_ROWS
        for dy in range(MODULE_ROWS):
            out.append(new_entity(belt, tile_position=(ORE_X, y0 + dy), direction=Direction.SOUTH))
            if dy != SPLITTER_ROW:
                out.append(new_entity(belt, tile_position=(PLATE_X, y0 + dy), direction=Direction.SOUTH))
        out.append(new_entity(pole, tile_position=(IN_X, y0 + POLE_ROW)))
        out.append(new_entity(pole, tile_position=(OUT_X, y0 + POLE_ROW)))
        out.append(
            new_entity(
                splitter,
                tile_position=(OUT_X, y0 + SPLITTER_ROW),
                direction=Direction.SOUTH,
                output_priority=SPLITTER_PRIORITY,
            )
        )
        out.append(new_entity(belt, tile_position=(OUT_X, y0 + SIDELOAD_ROW), direction=Direction.EAST))
        # A unloads from its bottom row, B from its top row; an odd count leaves the last module without B.
        for k, (top, row) in enumerate(((y0, y0 + FURNACE_SIZE - 1), (y0 + FURNACE_SIZE, y0 + FURNACE_SIZE))):
            if 2 * m + k >= n:
                break
            out.append(new_entity(furnace, tile_position=(FURNACE_X, top)))
            out.append(new_entity(inserter, tile_position=(IN_X, row), direction=Direction.WEST))
            out.append(new_entity(inserter, tile_position=(OUT_X, row), direction=Direction.WEST))

    total = n * per_furnace
    demand = {item: n * r for item, r in ratios.ingredients_per_second(furnace, recipe).items()}
    inputs = ", ".join(f"{r:.3f} {item}/s" for item, r in demand.items())
    notes = [f"{n} x {furnace}: {total:.3f} {recipe}/s from {inputs} ({per_furnace:.3f}/s each, base crafting speed, no modules)"]
    full = 2 * ratios.belt_lane_capacity(belt)
    if total > full + 1e-9:
        notes.append(
            f"WARNING: output {total:.2f}/s exceeds the {belt} capacity ({full:.2f}/s), so the plate belt will back up; "
            f"use a faster belt or fewer furnaces (max ~{int(full / per_furnace)})"
        )
    for item, r in demand.items():
        if r > full + 1e-9:
            notes.append(f"WARNING: {item} demand {r:.2f}/s exceeds the input {belt} capacity ({full:.2f}/s)")
    return out, notes
