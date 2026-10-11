"""spec dict -> validated blueprint string. Draftsman only warns on bad layouts; here every warning is a failure."""
import warnings
from dataclasses import dataclass, field, replace

from draftsman.blueprintable import Blueprint

from . import checks, generators
from .errors import BuildError, SpecError
from .generators import Port

# flow direction (N=0 E=4 S=8 W=12) -> one tile along it
STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}


@dataclass
class BuildResult:
    string: str
    blueprint: Blueprint
    notes: list[str] = field(default_factory=list)
    # tiles relative to the blueprint's top-left tile (see `origin`)
    ports: list[Port] = field(default_factory=list)


def origin(bp: Blueprint) -> tuple[int, int]:
    """The blueprint's bounding-box top-left: the minimum tile_position x and y over all entities."""
    tiles = [e.tile_position for e in bp.entities]
    if not tiles:
        return 0, 0
    return min(t.x for t in tiles), min(t.y for t in tiles)


def check_ports(bp: Blueprint, ports: list[Port]) -> list[str]:
    """Every port (tile relative to `origin(bp)`) sits on a belt of its declared name, flowing its way, at the
    belt's open end: the tile before an input and the tile after an output must be free, since that's where
    the belt gets fed or drained."""
    ox, oy = origin(bp)
    problems = []
    for p in ports:
        x, y = p.tile[0] + ox, p.tile[1] + oy
        where = f"{p.role} port {p.item} at {p.tile}"
        if p.role not in ("input", "output"):
            problems.append(f"{where}: role must be 'input' or 'output', got {p.role!r}")
            continue
        if p.direction not in STEP:
            problems.append(f"{where}: direction must be N=0, E=4, S=8 or W=12, got {p.direction!r}")
            continue
        here = bp.find_entities_filtered(position=(x + 0.5, y + 0.5))
        belt = next((e for e in here if e.name == p.belt), None)
        if belt is None:
            problems.append(f"{where}: no {p.belt} on that tile (found {_names(here)})")
            continue
        if belt.direction != p.direction:
            problems.append(f"{where}: the {p.belt} there flows {int(belt.direction)}, not {p.direction}")
        dx, dy = STEP[p.direction]
        if p.role == "input":
            bx, by, side = x - dx, y - dy, "start"
        else:
            bx, by, side = x + dx, y + dy, "end"
        beyond = bp.find_entities_filtered(position=(bx + 0.5, by + 0.5))
        if beyond:
            problems.append(f"{where}: the belt doesn't {side} there, {_names(beyond)} sits next in line at {(bx - ox, by - oy)}")
    return problems


def _names(es) -> str:
    return ", ".join(e.name for e in es) or "nothing"


def build(spec: dict) -> BuildResult:
    if not isinstance(spec, dict) or "type" not in spec:
        raise SpecError("spec must be an object with a 'type' field")
    generator = generators.get(spec["type"])

    problems: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        entities, notes, ports = generator(spec)
        bp = Blueprint()
        bp.label = spec.get("label", spec["type"])
        for e in entities:
            bp.entities.append(e)
        # Pasted blueprints keep only the wires they carry: the game won't join poles inside one.
        # Axis-only keeps the wiring a tidy grid; pole_network flags any pole this leaves unjoined.
        bp.generate_power_connections(only_axis=True)
        string = bp.to_string()
    problems += [f"{type(w.message).__name__}: {w.message}" for w in caught]
    for check in (*checks.ALL_CHECKS, *generators.CHECKS.get(spec["type"], ())):
        problems += check(bp)
    # generators give port tiles in their own coordinates; publish them relative to the top-left tile
    ox, oy = origin(bp)
    ports = [replace(p, tile=(p.tile[0] - ox, p.tile[1] - oy)) for p in ports]
    problems += check_ports(bp, ports)
    if problems:
        raise BuildError(problems)
    return BuildResult(string=string, blueprint=bp, notes=notes, ports=ports)
