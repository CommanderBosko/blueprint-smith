"""Building blocks shared by the furnace-column generators (smelting_column, steel_column).

Every column repeats a 6-row module of two 3x3 furnaces, A on top and B below. Their inserters pair up
at the machine boundary (technique T2): A loads and unloads from its bottom row, B from its top row, so
rows 0, 1, 4 and 5 of the inserter columns stay free for poles (row 1) and lane balancing.
Both belts run south down every row of every module, so items enter at row 0 and leave at the last row.
"""
import math

from draftsman.constants import Direction
from draftsman.data import entities

from .. import ratios
from ..errors import SpecError
from . import Port

FURNACE_SIZE = 3
MODULE_ROWS = 2 * FURNACE_SIZE
POLE_ROW = 1


def entity_option(spec: dict, key: str, default: str, kind: str) -> str:
    """spec[key] (or `default`) must name an entity whose prototype type is `kind`."""
    name = spec.get(key, default)
    if not isinstance(name, str) or entities.raw.get(name, {}).get("type") != kind:
        raise SpecError(f"'{key}' must name a {kind} entity, got {name!r}")
    return name


def column_furnace(spec: dict, generator: str) -> str:
    """The spec's furnace, which must be 3x3 to fit the module."""
    furnace = entity_option(spec, "furnace", "electric-furnace", "furnace")
    box = entities.raw[furnace]["collision_box"]
    if round(box[1][0] - box[0][0] + 0.2) != FURNACE_SIZE:
        raise SpecError(f"{generator} only supports 3x3 furnaces (electric-furnace), got {furnace!r}")
    return furnace


def machine_count(spec: dict, generator: str, furnace: str, recipe: str, unit: str) -> int:
    """How many `furnace`s the spec asks for: its 'count', or enough to make its 'rate' of `recipe`."""
    if ("count" in spec) == ("rate" in spec):
        raise SpecError(f"{generator} needs exactly one of 'count' or 'rate' ({unit} per second)")
    if "count" in spec:
        n = spec["count"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise SpecError("'count' must be a positive integer")
        return n
    rate = spec["rate"]
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise SpecError(f"'rate' must be a positive number ({unit} per second)")
    return ratios.machines_for_rate(furnace, recipe, rate)


def target_rate(spec: dict, n: int, per_machine: float) -> float:
    """The output a column must reach: the spec's 'rate', or what its 'count' machines make."""
    return float(spec["rate"]) if "rate" in spec else n * per_machine


def modules(n: int):
    """For an n-furnace column, yield each module's top row and its furnace slots as
    (furnace top row, inserter row) pairs. An odd n leaves the last module without B."""
    for m in range(math.ceil(n / 2)):
        y0 = m * MODULE_ROWS
        slots = ((y0, y0 + FURNACE_SIZE - 1), (y0 + FURNACE_SIZE, y0 + FURNACE_SIZE))
        yield y0, slots[: n - 2 * m]


def column_ports(n: int, belt: str, in_x: int, inputs: dict[str, float], out_x: int, product: str, rate: float) -> list[Port]:
    """Ports of an n-furnace column: each input item enters at the top of col `in_x`, `product` leaves
    at the bottom of col `out_x` at `rate`/s. `inputs` maps item -> demand per second."""
    last = math.ceil(n / 2) * MODULE_ROWS - 1
    south = int(Direction.SOUTH)
    ports = [Port("input", item, belt, (in_x, 0), south, r) for item, r in inputs.items()]
    ports.append(Port("output", product, belt, (out_x, last), south, rate))
    return ports
