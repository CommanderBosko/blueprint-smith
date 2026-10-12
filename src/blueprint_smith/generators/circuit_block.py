"""Green circuit block (M2, pieces E and F of docs/m2-plan.md): a cable plant feeds a circuit plant by direct
insertion, both under shared beacons, and the circuits fill both lanes of a stacked turbo belt.

Two layouts, picked by the `copper` option ("west" or "north"): the side copper comes in from. Only the copper belt,
its inserter and the iron belt's first tiles differ. K cable plant, C circuit plant, B beacon (each reaches both
plants), S substation; an inserter's arrow is the way it moves items.

"west" (the default): 13x11 tiles, approved by the user and confirmed in-game 2026-10-12 (both output lanes full).

     x -7 -6 -5 -4 -3 -2 -1  0  1  2  3  4  5
y -5     .  .  .  .  .  B  B  B  B  B  B  .  .
y -4     .  .  .  .  .  B  B  B  B  B  B  .  .
y -3     .  .  .  .  .  B  B  B  B  B  B  .  v
y -2     .  .  .  S  S  .  .  .  .  >  >  >  v    the stub side-loads onto the west lane (T5)
y -1     .  .  .  S  S  .  .  .  .  ^  ^  .  v
y  0     .  .  K  K  K  K  >  C  C  C  C  >  v
y  1    Cu  >  K  K  K  K  >  C  C  C  C  >  v    the east inserters fill the east lane (F1)
y  2     .  .  K  K  K  K  >  C  C  C  C  .  v
y  3     .  .  K  K  K  K  .  C  C  C  C  .  v
y  4     .  .  .  .  .  .  .  ^  ^  .  .  .  v
y  5    Fe  >  >  >  >  >  >  >  >  .  .  .  v    circuits out

"north": 11x11 tiles, approved by the user 2026-10-12. Copper comes down into the cable plant from a one-tile belt
beside the substation (its front is the substation), so the iron belt starts at x=-5 and the block loses 2 columns.

     x -5 -4 -3 -2 -1  0  1  2  3  4  5
y -5     .  .  .  B  B  B  B  B  B  .  .
y -4     .  .  .  B  B  B  B  B  B  .  .
y -3     .  .  .  B  B  B  B  B  B  .  v
y -2    Cu  S  S  .  .  .  .  >  >  >  v    stub (T5)
y -1     v  S  S  .  .  .  .  ^  ^  .  v
y  0     K  K  K  K  >  C  C  C  C  >  v
y  1     K  K  K  K  >  C  C  C  C  >  v
y  2     K  K  K  K  >  C  C  C  C  .  v
y  3     K  K  K  K  .  C  C  C  C  .  v
y  4     .  .  .  .  .  ^  ^  .  .  .  v
y  5    Fe  >  >  >  >  >  >  .  .  .  v    circuits out

Copper enters at (-7, 1) or (-5, -2) and iron at (-7, 5) or (-5, 5), both stacked and flowing east; circuits leave at
(5, 5). Every inserter's blueprint `direction` is the side it picks up from (F7). The rate, copper side, beacon count
(0-2) and inserter counts per link are spec options, and they're what the optimiser varies (`variants`). Defaults come
from the solver (effects.py) and the measured inserter rates (F28), sized so each link carries its demand at the
harness's 98% bar. `sizing` holds the link math the notes and `variants` share. The stub inserters sit at the east end
of the circuit plant's top edge, so the stub starts under the first of them and carries no idle belt (T5; the user's
in-game tweak, 2026-10-12).
"""
import itertools
import math
from dataclasses import dataclass

from draftsman.constants import Direction
from draftsman.data import entities
from draftsman.entity import new_entity

from .. import effects
from ..errors import SpecError
from . import Port, register
from .beaconed import BEACON, BELT, INSERTER, LANE, MARGIN, PLANT, PROD, SPEED, STACK, Link
from .beaconed import count as _count
from .beaconed import plant as _plant

POLE = "substation"
CIRCUIT, CABLE = "electronic-circuit", "copper-cable"
NORTH, EAST, SOUTH, WEST = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST

CABLE_AT, CIRCUIT_AT = (-5, 0), (0, 0)  # 4x4 plants, top-left tiles
# the `copper` option: the one-tile copper belt (flowing east), and the inserter that feeds the cable plant from it
# with the side it picks up from
COPPER_SIDES = ("west", "north")
COPPER_BELTS = {"west": (-7, 1), "north": (-5, -2)}
COPPER_INSERTERS = {"west": ((-6, 1), WEST), "north": ((-5, -1), NORTH)}
CABLE_X = -1  # hand-off inserters, rows 0-3
IRON_ROW, IRON_INSERTER_ROW = 5, 4
IRON_FROMS = {"west": -7, "north": -5}  # the iron belt runs east from here to under the inserters
OUT_X, OUT_TOP, OUT_BOTTOM = 5, -3, 5  # the output belt flows south down x=5
EAST_X = 4  # inserters onto the output belt, rows 0-3
STUB_Y, NORTH_Y = -2, -1  # inserters at y=-1 fill the stub, which flows east from under the first into the output belt's side
CIRCUIT_EAST = CIRCUIT_AT[0] + 3  # the circuit plant's east column: the stub inserters end here
BEACONS = ((-2, -5), (1, -5))
SUBSTATION = (-4, -2)
# inserter (pickup, drop) roles the layout allows; check_flow also needs each one at least once
FLOWS = {("copper belt", "cable plant"), ("cable plant", "circuit plant"), ("iron belt", "circuit plant"),
         ("circuit plant", "output belt"), ("circuit plant", "stub")}
BELT_FLOW = {"copper belt": EAST, "iron belt": EAST, "stub": EAST, "output belt": SOUTH}


def _belt_role(x: int, y: int) -> str | None:
    if x == OUT_X:
        return "output belt"
    if (x, y) in COPPER_BELTS.values():  # before the stub: the north copper belt sits on its row
        return "copper belt"
    if y == IRON_ROW and x < OUT_X:
        return "iron belt"
    if y == STUB_Y and 0 <= x < OUT_X:
        return "stub"
    return None


def _role(bp, pos) -> str | None:
    for e in bp.find_entities_filtered(position=tuple(pos)):
        kind = e.prototype.get("type")
        if kind == "assembling-machine":
            return {CABLE: "cable plant", CIRCUIT: "circuit plant"}.get(e.recipe, f"{e.recipe} plant")
        if kind == "transport-belt":
            return _belt_role(e.tile_position.x, e.tile_position.y) or "a stray belt"
    return None


def _where(e) -> str:
    return f"{e.name} at {tuple(e.global_position)}"


def check_flow(bp) -> list[str]:
    """Inserters move copper -> cable plant -> circuit plant and iron -> circuit plant, and the circuit plant
    unloads onto the output belt (its east lane) and the stub (side-loaded onto its west lane). Every move happens
    somewhere, the plants make what they're placed for, the belts flow as drawn, there's one copper belt (west or
    north), and the output belt runs straight past the stub, so the stub side-loads instead of turning into it (T5)."""
    problems = []
    want = {CABLE_AT: CABLE, CIRCUIT_AT: CIRCUIT}
    found = set()
    moves = set()
    for e in bp.entities:
        kind = e.prototype.get("type")
        at = (e.tile_position.x, e.tile_position.y)
        if kind == "assembling-machine":
            if want.get(at) != e.recipe:
                problems.append(f"{_where(e)} makes {e.recipe}; the layout has a {CABLE} plant at {CABLE_AT} and "
                                f"a {CIRCUIT} plant at {CIRCUIT_AT}")
            found.add(at)
        elif kind == "inserter":
            move = (_role(bp, e.pickup_position), _role(bp, e.drop_position))
            if move not in FLOWS:
                problems.append(f"{_where(e)} moves items from {move[0] or 'nothing'} to {move[1] or 'nothing'}")
            moves.add(move)
        elif kind == "transport-belt":
            role = _belt_role(*at)
            if role is None:
                problems.append(f"{_where(e)} isn't on one of the layout's belts")
            elif e.direction != BELT_FLOW[role]:
                problems.append(f"{_where(e)} on the {role} must flow {BELT_FLOW[role].name.lower()}")
    problems += [f"no {recipe} plant at {at}" for at, recipe in want.items() if at not in found]
    problems += [f"no inserter moves items from {a} to {b}" for a, b in sorted(FLOWS - moves)]
    belts = {(e.tile_position.x, e.tile_position.y) for e in bp.entities if e.prototype.get("type") == "transport-belt"}
    copper = sorted(t for t in belts if _belt_role(*t) == "copper belt")
    if len(copper) != 1:
        sides = " or ".join(f"{at} ({side})" for side, at in COPPER_BELTS.items())
        got = f"copper belts at {', '.join(map(str, copper))}" if copper else "no copper belt"
        problems.append(f"{got}: the layout has exactly one, at {sides}")
    stub = sorted(x for x, y in belts if _belt_role(x, y) == "stub")
    drops = [math.floor(e.drop_position.x) for e in bp.entities if e.prototype.get("type") == "inserter"
             and (_role(bp, e.pickup_position), _role(bp, e.drop_position)) == ("circuit plant", "stub")]
    if stub and drops and stub[0] < min(drops):
        problems.append(f"the stub starts at x={stub[0]}, west of its first inserter (it drops at x={min(drops)}): "
                        f"those belts carry nothing; start the stub under the first inserter (T5)")
    if stub and (gaps := sorted(set(range(stub[0], OUT_X)) - set(stub))):
        problems.append(f"the stub has no belt at x={', '.join(map(str, gaps))} on y={STUB_Y}: it must run unbroken "
                        f"into the output belt's side")
    for tile, what in (((OUT_X - 1, STUB_Y), "the stub's last tile"), ((OUT_X, STUB_Y), "the side-load tile"),
                       ((OUT_X, STUB_Y - 1), "the output belt above the side-load tile")):
        if tile not in belts:
            problems.append(f"no belt at {tile} ({what}): without the output belt running straight past it, the "
                            f"stub turns into the output belt instead of side-loading, and both lanes end up as one")
    return problems


def _rate_ok(rate) -> bool:
    return not isinstance(rate, bool) and isinstance(rate, (int, float)) and 0 < rate <= 2 * LANE


@dataclass(frozen=True)
class Sizing:
    circuit: effects.MachineRates
    cable_plant: effects.MachineRates
    iron: float  # iron plates/s, cable/s and copper plates/s needed for the rate
    cable: float
    copper: float
    links: tuple[Link, ...]  # copper, iron, cable hand-off, east lane, stub -> west lane
    bound: float  # the most circuits/s the block can make, with no safety margin


def sizing(rate: float, quality: str, beacons: int, n_iron: int, n_cable: int, n_east: int, n_north: int) -> Sizing:
    """The block's link math at `rate` circuits/s, shared by the notes and `variants` so they can't drift.

    Inserter rates are the measured legendary ones (F28). Each lane carries min(n x 80, 120)/s. The bound is the least
    of the circuit plant's capacity, the rate scaled by carries/demand for each input link (copper, iron, the cable
    hand-off) and by the cable plant's capacity over its demand, and the two lanes together."""
    measured = effects.LEGENDARY_STACK_INSERTER
    circuit, cable_plant = _plant(CIRCUIT, quality, beacons), _plant(CABLE, quality, beacons)
    need = circuit.demand(rate).ingredients
    iron, cable = need["iron-plate"], need[CABLE]
    copper = cable_plant.demand(cable).ingredients["copper-plate"]

    def lane(n: int) -> tuple[float, float]:
        # a full lane is an exact belt limit, so the margin only applies while the inserters are the limit
        carries = n * measured["machine_to_belt"]
        return (LANE, 1.0) if carries >= LANE else (carries, MARGIN)

    links = (
        Link("copper belt -> cable plant", 1, measured["belt_to_machine"], MARGIN, copper),
        Link("iron belt -> circuit plant", n_iron, n_iron * measured["belt_to_machine"], MARGIN, iron),
        Link("cable plant -> circuit plant", n_cable, n_cable * measured["machine_to_machine"], MARGIN, cable),
        Link("circuit plant -> east lane", n_east, *lane(n_east), rate / 2),
        Link("circuit plant -> stub -> west lane", n_north, *lane(n_north), rate / 2),
    )
    copper_link, iron_link, cable_link, east, west = links
    bound = min(circuit.products[CIRCUIT],
                *(rate * link.carries / link.demand for link in (copper_link, iron_link, cable_link)),
                rate * cable_plant.products[CABLE] / cable,
                east.carries + west.carries)
    return Sizing(circuit, cable_plant, iron, cable, copper, links, bound)


def variants(request: dict) -> list[dict]:
    """Specs for `request` ({"item", "rate"}, optionally "quality") that the solver says could pass the harness:
    every copper side, beacon count (0-2) and inserter count per link (1-4) whose `sizing` bound reaches 98% of the
    rate. Nothing for another item or a rate outside (0, 240]; an unknown quality raises SpecError."""
    if request.get("item") != CIRCUIT:
        return []
    rate = request.get("rate")
    if not _rate_ok(rate):
        return []
    quality = request.get("quality", "legendary")
    effects.quality_level(quality)  # raises SpecError for an unknown quality
    extra = {"quality": quality} if "quality" in request else {}
    fits = [(b, *counts) for b in range(len(BEACONS) + 1) for counts in itertools.product(range(1, 5), repeat=4)
            if sizing(rate, quality, b, *counts).bound >= MARGIN * rate - 1e-9]
    return [{"type": "circuit_block", "rate": rate, "copper": side, "beacons": b, "iron_inserters": n_iron,
             "cable_inserters": n_cable, "east_inserters": n_east, "north_inserters": n_north, **extra}
            for side in COPPER_SIDES for b, n_iron, n_cable, n_east, n_north in fits]


@register("circuit_block", checks=(check_flow,), variants=variants, research="all")
def circuit_block(spec: dict) -> tuple[list, list[str], list[Port]]:
    rate = spec.get("rate", 2 * LANE)
    if not _rate_ok(rate):
        raise SpecError(f"'rate' must be a number of {CIRCUIT}/s above 0 and at most {2 * LANE:g} (a stacked "
                        f"{BELT}), got {rate!r}")
    quality = spec.get("quality", "legendary")
    effects.quality_level(quality)  # raises SpecError for an unknown quality
    side = spec.get("copper", "west")
    if side not in COPPER_SIDES:
        raise SpecError(f"'copper' must be one of {', '.join(map(repr, COPPER_SIDES))} (the side copper comes in "
                        f"from), got {side!r}")
    measured = effects.LEGENDARY_STACK_INSERTER  # measured for legendary only (F28)

    # the fewest shared beacons (0-2) whose circuit plant makes the rate with the harness's margin to spare
    fits = [n for n in range(len(BEACONS) + 1) if _plant(CIRCUIT, quality, n).products[CIRCUIT] * MARGIN >= rate]
    beacons = _count(spec, "beacons", fits[0] if fits else len(BEACONS), 0, len(BEACONS))
    need = sizing(rate, quality, beacons, 1, 1, 1, 1)  # the demands don't depend on the inserter counts

    def enough(demand: float, each: float) -> int:
        return max(1, math.ceil(demand / (each * MARGIN) - 1e-9))

    n_iron = _count(spec, "iron_inserters", enough(need.iron, measured["belt_to_machine"]))
    n_cable = _count(spec, "cable_inserters", enough(need.cable, measured["machine_to_machine"]))
    lane_default = 1 if rate / 2 <= measured["machine_to_belt"] * MARGIN else 2
    n_east = _count(spec, "east_inserters", lane_default)
    n_north = _count(spec, "north_inserters", lane_default)
    s = sizing(rate, quality, beacons, n_iron, n_cable, n_east, n_north)

    out: list = []

    def add(name, at, **kw):
        out.append(new_entity(name, tile_position=at, **kw))
        return out[-1]

    for at, recipe in ((CABLE_AT, CABLE), (CIRCUIT_AT, CIRCUIT)):
        add(PLANT, at, recipe=recipe, quality=quality).request_modules(
            PROD, range(entities.raw[PLANT]["module_slots"]), quality=quality)
    for at in BEACONS[:beacons]:
        add(BEACON, at, quality=quality).request_modules(SPEED, range(entities.raw[BEACON]["module_slots"]),
                                                         quality=quality)
    add(POLE, SUBSTATION)
    inserters = [COPPER_INSERTERS[side]]
    inserters += [((CABLE_X, y), WEST) for y in range(n_cable)]
    inserters += [((x, IRON_INSERTER_ROW), SOUTH) for x in range(n_iron)]
    inserters += [((EAST_X, y), WEST) for y in range(n_east)]
    stub_from = CIRCUIT_EAST + 1 - n_north  # the stub inserters end at the plant's east column, by the output belt
    inserters += [((x, NORTH_Y), SOUTH) for x in range(stub_from, CIRCUIT_EAST + 1)]
    for at, picks_from in inserters:
        add(INSERTER, at, direction=picks_from, quality=quality)
    add(BELT, COPPER_BELTS[side], direction=EAST)
    for x in range(IRON_FROMS[side], n_iron):
        add(BELT, (x, IRON_ROW), direction=EAST)
    for x in range(stub_from, OUT_X):
        add(BELT, (x, STUB_Y), direction=EAST)
    for y in range(OUT_TOP, OUT_BOTTOM + 1):
        add(BELT, (OUT_X, y), direction=SOUTH)

    made, cable_made = s.circuit.products[CIRCUIT], s.cable_plant.products[CABLE]
    notes = [
        f"circuit plant: {beacons} beacon(s), crafting speed {s.circuit.crafting_speed:g}, productivity "
        f"+{s.circuit.productivity:.0%}: up to {made:.2f} {CIRCUIT}/s for {rate:g}/s ({rate / made:.0%} busy)",
        f"cable plant: crafting speed {s.cable_plant.crafting_speed:g}: up to {cable_made:.2f} {CABLE}/s for "
        f"{s.cable:.2f}/s ({s.cable / cable_made:.0%} busy)",
    ]
    if made < rate - 1e-9:
        notes.append(f"WARNING: the circuit plant makes {made:.2f}/s, under the {rate:g}/s target: add beacons")
    if cable_made < s.cable - 1e-9:
        notes.append(f"WARNING: the cable plant makes {cable_made:.2f} {CABLE}/s, under the {s.cable:.2f}/s needed")
    for link in s.links:
        notes.append(f"{link.name}: {link.inserters} stack inserter(s) carry {link.carries:.2f}/s for {link.demand:.2f}/s")
        if link.carries * link.margin < link.demand - 1e-9:
            notes.append(f"WARNING: {link.name} carries {link.carries:.2f}/s, under {link.demand:.2f}/s"
                         + (f" with the harness's {MARGIN:.0%} margin" if link.margin < 1 else ""))
    if quality != "legendary":
        notes.append(f"inserter rates are measured for legendary stack inserters only; at {quality} the harness decides")
    notes.append("the harness runs this type with all research (registered research=\"all\"): stacking items on belts "
                 "and the stack inserter's hand size need it")

    ports = [
        Port("input", "copper-plate", BELT, COPPER_BELTS[side], int(EAST), s.copper, STACK),
        Port("input", "iron-plate", BELT, (IRON_FROMS[side], IRON_ROW), int(EAST), s.iron, STACK),
        Port("output", CIRCUIT, BELT, (OUT_X, OUT_BOTTOM), int(SOUTH), float(rate), STACK),
    ]
    return out, notes, ports
