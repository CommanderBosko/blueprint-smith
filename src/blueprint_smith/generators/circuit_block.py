"""Green circuit block (M2, piece E of docs/m2-plan.md): a cable plant feeds a circuit plant by direct insertion,
both under shared beacons, and the circuits fill both lanes of a stacked turbo belt.

Layout in tile coordinates, approved by the user and confirmed in-game 2026-10-12 (both output lanes full). K cable plant, C circuit plant, B beacon (each reaches
both plants), S substation; an inserter's arrow is the way it moves items.

     x -7 -6 -5 -4 -3 -2 -1  0  1  2  3  4  5
y -5     .  .  .  .  .  B  B  B  B  B  B  .  .
y -4     .  .  .  .  .  B  B  B  B  B  B  .  .
y -3     .  .  .  .  .  B  B  B  B  B  B  .  v
y -2     .  .  .  S  S  .  .  >  >  >  >  >  v    the stub side-loads onto the west lane (T5)
y -1     .  .  .  S  S  .  .  ^  ^  .  .  .  v
y  0     .  .  K  K  K  K  >  C  C  C  C  >  v
y  1    Cu  >  K  K  K  K  >  C  C  C  C  >  v    the east inserters fill the east lane (F1)
y  2     .  .  K  K  K  K  >  C  C  C  C  .  v
y  3     .  .  K  K  K  K  .  C  C  C  C  .  v
y  4     .  .  .  .  .  .  .  ^  ^  .  .  .  v
y  5    Fe  >  >  >  >  >  >  >  >  .  .  .  v    circuits out

Copper enters at (-7, 1) and iron at (-7, 5), both stacked; circuits leave at (5, 5). Every inserter's blueprint
`direction` is the side it picks up from (F7). The rate, beacon count (0-2) and inserter counts per link are spec
options, and they're what the optimiser varies. Defaults come from the solver (effects.py) and the measured
inserter rates (F28), sized so each link carries its demand at the harness's 98% bar.
"""
import math

from draftsman.constants import Direction
from draftsman.data import entities
from draftsman.entity import new_entity

from .. import effects, ratios
from ..errors import SpecError
from . import Port, register

PLANT, BEACON, BELT, INSERTER, POLE = "electromagnetic-plant", "beacon", "turbo-transport-belt", "stack-inserter", "substation"
CIRCUIT, CABLE = "electronic-circuit", "copper-cable"
PROD, SPEED = "productivity-module-3", "speed-module-3"
STACK = 4  # items per belt slot once belt stacking is researched
MARGIN = 0.98  # the harness's output bar
LANE = ratios.belt_lane_capacity(BELT) * STACK  # 120/s on a stacked turbo lane
EAST, SOUTH, WEST = Direction.EAST, Direction.SOUTH, Direction.WEST

CABLE_AT, CIRCUIT_AT = (-5, 0), (0, 0)  # 4x4 plants, top-left tiles
COPPER_BELT, COPPER_INSERTER = (-7, 1), (-6, 1)
CABLE_X = -1  # hand-off inserters, rows 0-3
IRON_ROW, IRON_INSERTER_ROW, IRON_FROM = 5, 4, -7  # the iron belt runs east from x=-7 to under the inserters
OUT_X, OUT_TOP, OUT_BOTTOM = 5, -3, 5  # the output belt flows south down x=5
EAST_X = 4  # inserters onto the output belt, rows 0-3
STUB_Y, NORTH_Y = -2, -1  # inserters at y=-1 fill the stub, which flows east from x=0 into the output belt's side
BEACONS = ((-2, -5), (1, -5))
SUBSTATION = (-4, -2)
# inserter (pickup, drop) roles the layout allows; check_flow also needs each one at least once
FLOWS = {("copper belt", "cable plant"), ("cable plant", "circuit plant"), ("iron belt", "circuit plant"),
         ("circuit plant", "output belt"), ("circuit plant", "stub")}
BELT_FLOW = {"copper belt": EAST, "iron belt": EAST, "stub": EAST, "output belt": SOUTH}


def _belt_role(x: int, y: int) -> str | None:
    if x == OUT_X:
        return "output belt"
    if (x, y) == COPPER_BELT:
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
    somewhere, the plants make what they're placed for, the belts flow as drawn, and the output belt runs straight
    past the stub, so the stub side-loads instead of turning into it (T5)."""
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
    for tile, what in (((OUT_X - 1, STUB_Y), "the stub's last tile"), ((OUT_X, STUB_Y), "the side-load tile"),
                       ((OUT_X, STUB_Y - 1), "the output belt above the side-load tile")):
        if tile not in belts:
            problems.append(f"no belt at {tile} ({what}): without the output belt running straight past it, the "
                            f"stub turns into the output belt instead of side-loading, and both lanes end up as one")
    return problems


def _count(spec: dict, key: str, default: int, low: int = 1, high: int = 4) -> int:
    n = spec.get(key, default)
    if isinstance(n, bool) or not isinstance(n, int) or not low <= n <= high:
        raise SpecError(f"'{key}' must be an integer from {low} to {high}, got {n!r}")
    return n


def _plant(recipe: str, quality: str, beacons: int) -> effects.MachineRates:
    slots = entities.raw[PLANT]["module_slots"]
    beacon = effects.Beacon(((SPEED, quality),) * entities.raw[BEACON]["module_slots"], quality)
    return effects.machine_rates(PLANT, recipe, quality=quality, modules=[(PROD, quality)] * slots,
                                 beacons=[beacon] * beacons, research="all")


@register("circuit_block", checks=(check_flow,))
def circuit_block(spec: dict) -> tuple[list, list[str], list[Port]]:
    rate = spec.get("rate", 2 * LANE)
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= 2 * LANE:
        raise SpecError(f"'rate' must be a number of {CIRCUIT}/s above 0 and at most {2 * LANE:g} (a stacked "
                        f"{BELT}), got {rate!r}")
    quality = spec.get("quality", "legendary")
    effects.quality_level(quality)  # raises SpecError for an unknown quality
    measured = effects.LEGENDARY_STACK_INSERTER  # measured for legendary only (F28)

    # the fewest shared beacons (0-2) whose circuit plant makes the rate with the harness's margin to spare
    fits = [n for n in range(len(BEACONS) + 1) if _plant(CIRCUIT, quality, n).products[CIRCUIT] * MARGIN >= rate]
    beacons = _count(spec, "beacons", fits[0] if fits else len(BEACONS), 0, len(BEACONS))
    circuit, cable_plant = _plant(CIRCUIT, quality, beacons), _plant(CABLE, quality, beacons)
    need = circuit.demand(rate).ingredients
    iron, cable = need["iron-plate"], need[CABLE]
    copper = cable_plant.demand(cable).ingredients["copper-plate"]

    def enough(demand: float, each: float) -> int:
        return max(1, math.ceil(demand / (each * MARGIN) - 1e-9))

    n_iron = _count(spec, "iron_inserters", enough(iron, measured["belt_to_machine"]))
    n_cable = _count(spec, "cable_inserters", enough(cable, measured["machine_to_machine"]))
    lane_default = 1 if rate / 2 <= measured["machine_to_belt"] * MARGIN else 2
    n_east = _count(spec, "east_inserters", lane_default)
    n_north = _count(spec, "north_inserters", lane_default)

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
    inserters = [(COPPER_INSERTER, WEST)]
    inserters += [((CABLE_X, y), WEST) for y in range(n_cable)]
    inserters += [((x, IRON_INSERTER_ROW), SOUTH) for x in range(n_iron)]
    inserters += [((EAST_X, y), WEST) for y in range(n_east)]
    inserters += [((x, NORTH_Y), SOUTH) for x in range(n_north)]
    for at, picks_from in inserters:
        add(INSERTER, at, direction=picks_from, quality=quality)
    add(BELT, COPPER_BELT, direction=EAST)
    for x in range(IRON_FROM, n_iron):
        add(BELT, (x, IRON_ROW), direction=EAST)
    for x in range(0, OUT_X):
        add(BELT, (x, STUB_Y), direction=EAST)
    for y in range(OUT_TOP, OUT_BOTTOM + 1):
        add(BELT, (OUT_X, y), direction=SOUTH)

    made, cable_made = circuit.products[CIRCUIT], cable_plant.products[CABLE]
    notes = [
        f"circuit plant: {beacons} beacon(s), crafting speed {circuit.crafting_speed:g}, productivity "
        f"+{circuit.productivity:.0%}: up to {made:.2f} {CIRCUIT}/s for {rate:g}/s ({rate / made:.0%} busy)",
        f"cable plant: crafting speed {cable_plant.crafting_speed:g}: up to {cable_made:.2f} {CABLE}/s for "
        f"{cable:.2f}/s ({cable / cable_made:.0%} busy)",
    ]
    if made < rate - 1e-9:
        notes.append(f"WARNING: the circuit plant makes {made:.2f}/s, under the {rate:g}/s target: add beacons")
    if cable_made < cable - 1e-9:
        notes.append(f"WARNING: the cable plant makes {cable_made:.2f} {CABLE}/s, under the {cable:.2f}/s needed")
    def lane(n: int) -> tuple[float, float]:
        # a full lane is an exact belt limit, so the margin only applies while the inserters are the limit
        carries = n * measured["machine_to_belt"]
        return (LANE, 1.0) if carries >= LANE else (carries, MARGIN)

    links = [
        ("copper belt -> cable plant", 1, measured["belt_to_machine"], MARGIN, copper),
        ("iron belt -> circuit plant", n_iron, n_iron * measured["belt_to_machine"], MARGIN, iron),
        ("cable plant -> circuit plant", n_cable, n_cable * measured["machine_to_machine"], MARGIN, cable),
        ("circuit plant -> east lane", n_east, *lane(n_east), rate / 2),
        ("circuit plant -> stub -> west lane", n_north, *lane(n_north), rate / 2),
    ]
    for link, n, carries, margin, demand in links:
        notes.append(f"{link}: {n} stack inserter(s) carry {carries:.2f}/s for {demand:.2f}/s")
        if carries * margin < demand - 1e-9:
            notes.append(f"WARNING: {link} carries {carries:.2f}/s, under {demand:.2f}/s"
                         + (f" with the harness's {MARGIN:.0%} margin" if margin < 1 else ""))
    if quality != "legendary":
        notes.append(f"inserter rates are measured for legendary stack inserters only; at {quality} the harness decides")
    notes.append("evaluate with --research all: stacking items on belts and the stack inserter's hand size need it")

    ports = [
        Port("input", "copper-plate", BELT, COPPER_BELT, int(EAST), copper, STACK),
        Port("input", "iron-plate", BELT, (IRON_FROM, IRON_ROW), int(EAST), iron, STACK),
        Port("output", CIRCUIT, BELT, (OUT_X, OUT_BOTTOM), int(SOUTH), float(rate), STACK),
    ]
    return out, notes, ports
