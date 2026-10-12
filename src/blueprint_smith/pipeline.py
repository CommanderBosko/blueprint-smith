"""spec dict -> validated blueprint string. Draftsman only warns on bad layouts; here every warning is a failure."""
import warnings
from dataclasses import dataclass, field, replace

from draftsman.blueprintable import Blueprint
from draftsman.entity import new_entity

from . import checks, generators
from .errors import BuildError, SpecError
from .generators import Port

# flow direction (N=0 E=4 S=8 W=12) -> one tile along it
STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}
LABEL = "display-panel"  # shows each input's item (P3); a label, not part of the block
LABEL_GAP = 2  # tiles from an input's first belt to its label: one free tile between, where the supply belt joins
DIRECTION = {v: k for k, v in STEP.items()}
SPLITTER = {"transport-belt": "splitter", "fast-transport-belt": "fast-splitter",
            "express-transport-belt": "express-splitter", "turbo-transport-belt": "turbo-splitter"}


@dataclass
class BuildResult:
    string: str
    blueprint: Blueprint
    notes: list[str] = field(default_factory=list)
    # tiles relative to the blueprint's top-left tile (see `origin`)
    ports: list[Port] = field(default_factory=list)


def origin(bp: Blueprint) -> tuple[int, int]:
    """The block's top-left: the minimum tile_position x and y over all entities but the input labels (P3)."""
    tiles = [e.tile_position for e in bp.entities if e.name != LABEL]
    if not tiles:
        return 0, 0
    return min(t.x for t in tiles), min(t.y for t in tiles)


def check_ports(bp: Blueprint, ports: list[Port]) -> list[str]:
    """Every port (tile relative to `origin(bp)`, stack 1-4) sits on a belt of its declared name, flowing its
    way, at the belt's open end: the tile before an input and the tile after an output must be free, since that's
    where the belt gets fed or drained."""
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
        if isinstance(p.stack, bool) or not isinstance(p.stack, int) or not 1 <= p.stack <= 4:
            problems.append(f"{where}: stack must be an integer from 1 to 4 (items per belt slot), got {p.stack!r}")
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


def labels(ports: list[Port]) -> list:
    """A display panel showing each input's item, LABEL_GAP tiles upstream of its first belt (P3)."""
    out = []
    for p in ports:
        if p.role != "input" or p.direction not in STEP:
            continue  # check_ports reports a bad port
        dx, dy = STEP[p.direction]
        panel = new_entity(LABEL, tile_position=(p.tile[0] - LABEL_GAP * dx, p.tile[1] - LABEL_GAP * dy))
        panel.icon = {"type": "item", "name": p.item}
        out.append(panel)
    return out


def check_labels(bp: Blueprint, ports: list[Port]) -> list[str]:
    """Every input port (tile relative to `origin(bp)`) has a display panel showing its item LABEL_GAP tiles
    upstream of its first belt (P3)."""
    ox, oy = origin(bp)
    problems = []
    for p in ports:
        if p.role != "input" or p.direction not in STEP:
            continue
        dx, dy = STEP[p.direction]
        x, y = p.tile[0] + ox - LABEL_GAP * dx, p.tile[1] + oy - LABEL_GAP * dy
        panels = [e for e in bp.find_entities_filtered(position=(x + 0.5, y + 0.5)) if e.name == LABEL]
        shows = [e.icon.name if e.icon else None for e in panels]
        if p.item not in shows:
            problems.append(f"input port {p.item} at {p.tile}: no {LABEL} showing {p.item} at "
                            f"{(x - ox, y - oy)} (found {shows or 'none'})")
    return problems


def _balancer_layout(direction: int) -> list[tuple[int, int, str, int]]:
    """The lane balancer after an output belt's end (P4, T11), as (forward, right, kind, flow direction) per tile:
    forward counts tiles past the old end along the flow, right counts tiles to the flow's right. A splitter halves
    the belt; one half curves out to the left, the other runs straight on the right, and both turn back in to
    side-load the middle belt from opposite sides, so each lane gets half of both lanes."""
    dx, dy = STEP[direction]
    right, left = DIRECTION[(-dy, dx)], DIRECTION[(dy, -dx)]
    return [
        (1, 0, "splitter", direction),  # covers right 0 and 1
        (2, 1, "belt", direction), (3, 1, "belt", left),  # the right half: on, then in
        (2, 0, "belt", left), (2, -1, "belt", direction), (3, -1, "belt", right),  # the left half: out, on, in
        (3, 0, "belt", direction),  # both side-load here: the new output end
    ]


def _balancer_tile(port: Port, forward: int, right: int, end: int = 0) -> tuple[int, int]:
    """The tile `forward` past `port`'s tile along its flow and `right` to its right, `end` tiles back."""
    dx, dy = STEP[port.direction]
    f = forward - end
    return port.tile[0] + f * dx - right * dy, port.tile[1] + f * dy + right * dx


def balancers(ports: list[Port]) -> tuple[list, list[Port]]:
    """A lane balancer after each belt output's end (P4, T11), and the ports with each output moved to its
    balancer's end."""
    out, moved = [], []
    for p in ports:
        if p.role != "output" or p.direction not in STEP or p.belt not in SPLITTER:
            moved.append(p)  # check_ports and check_balancers report these
            continue
        for forward, right, kind, flow in _balancer_layout(p.direction):
            x, y = _balancer_tile(p, forward, right)
            if kind == "splitter":
                x2, y2 = _balancer_tile(p, forward, right + 1)
                out.append(new_entity(SPLITTER[p.belt], position=((x + x2) / 2 + 0.5, (y + y2) / 2 + 0.5),
                                      direction=flow))
            else:
                out.append(new_entity(p.belt, tile_position=(x, y), direction=flow))
        moved.append(replace(p, tile=_balancer_tile(p, 3, 0)))
    return out, moved


def check_balancers(bp: Blueprint, ports: list[Port]) -> list[str]:
    """Every output port (tile relative to `origin(bp)`) ends a lane balancer of its belt's tier (P4, T11)."""
    ox, oy = origin(bp)
    problems = []
    for p in ports:
        if p.role != "output" or p.direction not in STEP:
            continue
        where = f"output port {p.item} at {p.tile}"
        if p.belt not in SPLITTER:
            problems.append(f"{where}: no splitter for {p.belt}, so no lane balancer")
            continue
        for forward, right, kind, flow in _balancer_layout(p.direction):
            x, y = _balancer_tile(p, forward, right, end=3)
            name = SPLITTER[p.belt] if kind == "splitter" else p.belt
            here = bp.find_entities_filtered(position=(x + ox + 0.5, y + oy + 0.5))
            if not any(e.name == name and int(e.direction) == flow for e in here):
                problems.append(f"{where}: its lane balancer needs a {name} flowing {flow} at {(x, y)} "
                                f"(found {_names(here)})")
            if kind == "splitter":
                x2, y2 = _balancer_tile(p, forward, right + 1, end=3)
                here2 = bp.find_entities_filtered(position=(x2 + ox + 0.5, y2 + oy + 0.5))
                if not set(map(id, here)) & set(map(id, here2)):
                    problems.append(f"{where}: its lane balancer's splitter must cover {(x, y)} and {(x2, y2)}")
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
        # the generator's own checks and ports judge its layout alone, before the pipeline adds the ends every
        # block gets; a port off its belt end would put them in the wrong place, so they wait for good ports
        for check in generators.CHECKS.get(spec["type"], ()):
            problems += check(bp)
        ox, oy = origin(bp)
        port_problems = check_ports(bp, [replace(p, tile=(p.tile[0] - ox, p.tile[1] - oy)) for p in ports])
        problems += port_problems
        if not port_problems:
            balanced, ports = balancers(ports)
            for e in [*balanced, *labels(ports)]:
                bp.entities.append(e)
        # Pasted blueprints keep only the wires they carry: the game won't join poles inside one.
        # Axis-only keeps the wiring a tidy grid; pole_network flags any pole this leaves unjoined.
        bp.generate_power_connections(only_axis=True)
        string = bp.to_string()
    problems += [f"{type(w.message).__name__}: {w.message}" for w in caught]
    for check in checks.ALL_CHECKS:
        problems += check(bp)
    # generators give port tiles in their own coordinates; publish them relative to the top-left tile
    ox, oy = origin(bp)
    ports = [replace(p, tile=(p.tile[0] - ox, p.tile[1] - oy)) for p in ports]
    if not port_problems:
        problems += check_ports(bp, ports) + check_labels(bp, ports) + check_balancers(bp, ports)
    if problems:
        raise BuildError(problems)
    return BuildResult(string=string, blueprint=bp, notes=notes, ports=ports)
