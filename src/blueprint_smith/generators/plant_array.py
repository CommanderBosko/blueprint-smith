"""Plant array (M2b, docs/red-circuits-plan.md): a beaconed array of product plants (P), each handed an
intermediate by direct insertion from an intermediate plant (K) beside it, in two mirrored rows around one shared
beacon row. Generic over the recipe: the product's other ingredients (one or two "near" items) come in on one belt
per row, one item per lane, and the intermediate's single ingredient (the "far" item) on a belt one row further out,
reached by long-handed inserters. Red circuits are the first recipe: green | plastic near, copper far, cable between.
Layout approved by the user 2026-10-12.

The default red block, 42x21 before the pipeline's ends (input labels, P3; the output's lane balancer, P4: 45x21
with it). S splitter, u/n underground entrance/exit, i stack inserter, L long-handed inserter, | medium pole,
B beacon; belt arrows are their flow.

          x -8      -1 0         1         2         3
             87654321012345678901234567890123456789012 3
y -3         >S>>>>>>>>>>>>>>>>>>>>>>>>>>>.............   row A's far belt (copper), to its last L
y -2         .Sv...>>>>>>>>>>>>>>>>>>>>>>>>>>>.........   row A's near belt (green | plastic), to its last i
y -1         ..u..>^<|i..|LL..|i....i..|LL..|i....|....
y  0         >>>>S^.^PPPPiKKKKiPPPPPPPPiKKKKiPPPPBBB...   K hands cable to the P either side; the east beacon
y  1         ....Sv.^PPPP.KKKK.PPPPPPPP.KKKK.PPPPBBB...   gives the last P a 5th
y  2         .....u.^PPPP.KKKK.PPPPPPPP.KKKK.PPPPBBB...
y  3         >>>>>>S^PPPP.KKKK.PPPPPPPP.KKKK.PPPP......
y  4         ..n..nSv|.ii|....|.iiSv.ii|....|..ii.|....   2 output inserters a P (T7); the lane reset S, v (T12)
y  5         ..v..u.u..>>>>>>>>>>>S>>>>>>>>>>>>>>>>>>>v   output A: row A on its south lane (F1)
y  6         ..v..BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBv   the shared beacon row: 4 per plant (F24)
y  7         ..v..BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB>   the port at x=33: both outputs side-load it (T9)
y  8         ..v..BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB^
y  9         ..v..n.n..>>>>>>>>>>>S>>>>>>>>>>>>>>>>>>>^   output B: row B on its north lane
y 10         ..v..>v<|.ii|....|.iiS^.ii|....|..ii.|....   row B's riser M, right under the band
y 11..17     row B: rows -3..4 mirrored about y=7, its near belt fed down x=-2 from M

The west front end (x -8..-1) splits each input belt between the rows. Copper (port at y=-3) splits at once: row
A's far belt runs on east, and row B's comes down x=-6, hopping under both near items' belts in one go. Green
(port at y=0) splits at x=-4 to run up and down x=-3; plastic (port at y=3) runs under green's hop and splits at
x=-2 to run up and down x=-1. Row A's near belt starts at a one-tile riser M at (-2, -1) that green side-loads
from the west and plastic from the east, so each item gets one lane (F3); M has nothing behind it. Row B's risers
hop under the beacon row's west beacon, which gives the first P its 4th, and meet at row B's M at (-2, 10) as
they surface; one belt runs down x=-2 to row B's near belt. The copper hop and row B's early merge are the user's,
from their in-game copy (2026-10-12).

Every inserter's blueprint `direction` is the side it picks up from (F7). Each output belt carries its row on the
lane next to the beacons. Halfway along, a lane reset (T12, the user's, 2026-10-12) moves that lane onto the other
one with a priority splitter and a side-load, so the row's last plants find an empty lane. At the east end both
outputs run past the band, turn in, and side-load the middle
belt at y=7 from opposite sides: one row a lane, no undergrounds (F3, T9; the user's, 2026-10-12). Medium poles sit
in the inserter rows over each hand-off gap and at both row ends. Sizing comes from the solver (effects.py), each
plant's beacons counted from the geometry (F24), and the measured legendary inserter rates (F28-F30).
"""
import itertools
import math
from dataclasses import dataclass

from draftsman.constants import Direction
from draftsman.data import entities, recipes
from draftsman.entity import new_entity

from .. import effects
from ..errors import SpecError
from . import Port, register
from .beaconed import BEACON, BELT, INSERTER, LANE, MARGIN, PLANT, PROD, SPEED, STACK, Link, count, modules, plant

LONG, POLE = "long-handed-inserter", "medium-electric-pole"
SPLITTER, UNDERGROUND = "turbo-splitter", "turbo-underground-belt"
NORTH, EAST, SOUTH, WEST = Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST
# the in-block intermediate each product recipe is built around; the product's other ingredients are the near items
INTERMEDIATES = {"advanced-circuit": "copper-cable", "electronic-circuit": "copper-cable"}

# row A's bands; row B is their mirror image, y -> MIRROR - y (for an entity, its bottom tile maps to its top)
FAR_Y, NEAR_Y, IN_Y, ROW_Y, OUT_IN_Y, OUT_Y, BAND_Y = -3, -2, -1, 0, 4, 5, 6
MIRROR = 14
OUT_B_Y = MIRROR - OUT_Y  # 9
MERGE_Y = (OUT_Y + OUT_B_Y) // 2  # 7: the beacon row's middle, where both outputs side-load one belt (T9)
PLANT_SIZE, BEACON_SIZE = 4, 3
PORT_X = -8  # every input port's tile column: the front end's west edge
M_X = -2  # the one-tile riser where the near items meet; its start is at (M_X, IN_Y)
M_B_Y = MIRROR - (BAND_Y - 1) + 1  # 10: row B's riser, where its near items surface from under the band
WEST_BEACON_X = -3  # the band's first beacon sits over the front end's risers
# a full lane's share of a plant's time it can spend blocked before the machine bar fails it (P2)
BLOCKED_MAX = 0.05
# inserters per plant edge: near and output on a P's 4-tile edges (one may hold a pole), long-handed on a K's top
# edge, hand-offs down a gap; (spec key, most)
COUNTS = (("near_inserters", 2), ("hand_inserters", 2), ("far_inserters", 4), ("output_inserters", 2))
MOST = tuple(high for _, high in COUNTS)


def mirror(y: int, height: int = 1) -> int:
    return MIRROR - (y + height - 1)


@dataclass(frozen=True)
class Row:
    """One row's x layout: product plants (P), intermediate plants (K) and the hand-off gaps between them."""
    products: tuple[int, ...]  # each P's left column, west to east
    intermediates: tuple[int, ...]  # each K's left column
    gaps: tuple[tuple[int, int, int], ...]  # (column, K's left column, P's left column) for each hand-off
    end: int  # first column east of the row

    @property
    def feeds(self) -> dict[int, tuple[int, ...]]:
        """K's left column -> the P columns it hands to."""
        out: dict[int, list[int]] = {}
        for _, k, p in self.gaps:
            out.setdefault(k, []).append(p)
        return {k: tuple(ps) for k, ps in out.items()}


def row_layout(n: int) -> Row:
    """n product plants in pairs around an intermediate plant (P > K < P), pairs touching; an odd last one is
    K > P, so a P always ends the row."""
    products, intermediates, gaps = [], [], []
    x = 0
    for i in range(0, n, 2):
        if i + 1 < n:
            products += [x, x + 10]
            intermediates.append(x + 5)
            gaps += [(x + 4, x + 5, x), (x + 9, x + 5, x + 10)]
            x += 14
        else:
            intermediates.append(x)
            products.append(x + 5)
            gaps.append((x + 4, x, x + 5))
            x += 9
    return Row(tuple(products), tuple(intermediates), tuple(gaps), x)


def band(row: Row) -> list[int]:
    """The shared beacon row's columns: every 3 tiles from over the front end until the last P has 4 (F24)."""
    last = max(row.products) + PLANT_SIZE - 1 + 3  # a beacon may start 2 tiles of gap past a machine's east edge
    return list(range(WEST_BEACON_X, last + 1, BEACON_SIZE))


def _reaches(bx: int, by: int, px: int, py: int) -> bool:
    """A beacon at (bx, by) reaches the plant at (px, py): its footprint grown by its supply distance overlaps the
    plant's collision box (F24)."""
    d = entities.raw[BEACON]["supply_area_distance"]
    (x1, y1), (x2, y2) = entities.raw[PLANT]["collision_box"]
    cx = cy = PLANT_SIZE / 2
    return (px + cx + x1 < bx + BEACON_SIZE + d and px + cx + x2 > bx - d
            and py + cy + y1 < by + BEACON_SIZE + d and py + cy + y2 > by - d)


def beacon_counts(row: Row, east_beacon: bool) -> tuple[dict[int, int], dict[int, int]]:
    """Beacons reaching each P and each K of row A (row B mirrors it): {left column: count}."""
    beacons = [(x, BAND_Y) for x in band(row)] + ([(row.end, ROW_Y)] if east_beacon else [])

    def n(px):
        return sum(_reaches(bx, by, px, ROW_Y) for bx, by in beacons)

    return {p: n(p) for p in row.products}, {k: n(k) for k in row.intermediates}


def pole_columns(row: Row) -> list[int]:
    """Medium poles in every inserter row: over the hand-off gaps, at the row's west edge (reaching the band's west
    beacon) and just past its east end (the east beacons). Neighbours are at most 9 apart (wire reach)."""
    return sorted({0, *(g for g, _, _ in row.gaps), row.end + 1})


def _powered(columns: list[int]) -> set[int]:
    reach = int(entities.raw[POLE]["supply_area_distance"])  # 3 tiles either side of the pole's own column (F10)
    return {x for c in columns for x in range(c - reach, c + reach + 1)}


def inserter_columns(left: int, poles: list[int]) -> list[int]:
    """A plant's edge tiles an inserter can use: powered, and not a pole's tile."""
    powered = _powered(poles)
    return [x for x in range(left, left + PLANT_SIZE) if x in powered and x not in poles]


def reset_after(row: Row) -> int:
    """How many of a row's P (west to east) unload before its lane reset (T12): half, rounded down. 0 means none."""
    return len(row.products) // 2


def reset_column(row: Row, poles: list[int], n_out: int) -> int | None:
    """The column of the lane reset's splitter (T12): the first x between the last output inserter before the reset
    and the first one after it where x and x + 1 are free in the output inserter row (the splitter's other half and
    the side-load belt). None for a row too short to reset, or with no room."""
    h = reset_after(row)
    if h == 0:
        return None
    ps = sorted(row.products)
    lo = max(inserter_columns(ps[h - 1], poles)[-n_out:]) + 1
    hi = min(inserter_columns(ps[h], poles)[-n_out:]) - 1
    return next((x for x in range(lo, hi) if x not in poles and x + 1 not in poles), None)


@dataclass(frozen=True)
class Recipe:
    product: str  # the product recipe, and the item it makes
    intermediate: str  # the in-block intermediate recipe, handed over by direct insertion
    near: tuple[str, ...]  # the product's other ingredients, on the near belt (one per lane)
    far: str  # the intermediate's one ingredient, on the far belt


def recipe_for(item) -> Recipe:
    if item not in INTERMEDIATES:
        raise SpecError(f"'item' must be one of {', '.join(map(repr, sorted(INTERMEDIATES)))}, got {item!r}")
    middle = INTERMEDIATES[item]

    def ingredients(r):
        return [i["name"] for i in recipes.raw[r]["ingredients"]]

    near = tuple(i for i in ingredients(item) if i != middle)
    (far,) = ingredients(middle)
    return Recipe(item, middle, near, far)


@dataclass(frozen=True)
class Sizing:
    products: dict[int, effects.MachineRates]  # each P of a row (by left column) at its beacon count
    intermediates: dict[int, effects.MachineRates]  # each K
    capacity: float  # products/s one row's plants can make, before its lane caps it
    row: float  # products/s one row can deliver: the least of its plants, links and its output lane
    links: tuple[Link, ...]  # the tightest instance of each link, per row
    bound: float  # the most products/s the block can deliver (both rows), with no safety margin


def sizing(rate: float, quality: str, recipe: Recipe, row: Row, east_beacon: bool, n_near: int, n_hand: int,
           n_far: int, n_out: int) -> Sizing:
    """The block's link math at `rate` products/s, shared by the notes and `variants` so they can't drift. Each row
    carries half the rate. A P's near link carries n_near x 87.47/s of both near items (F30) and its hand-off from K
    n_hand x 120/s (F28); a K's far link carries n_far x 13.33/s (F29) and scales the P's it feeds by that and its
    own capacity. Output inserters drop only into free slots (F1, T7): a P's n_out inserters carry n_out x 80/s
    (F28) times the share of its lane still free when the lane reaches it, so the last P's need the most. The row
    delivers its plants in lane order, west to east, up to the lane's 120/s.

    The lane reset (T12) empties the far lane halfway, but this deliberately doesn't credit it. Credited, it passes
    1 output inserter a P, and the harness fails that (2026-10-12: a P's output grew past the bar). Uncredited, the
    model is pessimistic in the same place the harness is strict."""
    stack, long = effects.LEGENDARY_STACK_INSERTER, effects.LEGENDARY_LONG_INSERTER
    p_beacons, k_beacons = beacon_counts(row, east_beacon)
    products = {p: plant(recipe.product, quality, n) for p, n in p_beacons.items()}
    middles = {k: plant(recipe.intermediate, quality, n) for k, n in k_beacons.items()}
    made = {p: m.products[recipe.product] for p, m in products.items()}

    def need(p, out):  # the P at `p`'s ingredients/s for `out` products/s
        return products[p].demand(out).ingredients

    capped = {}
    for p in row.products:
        ins = need(p, made[p])
        near = sum(ins[i] for i in recipe.near)
        capped[p] = min(made[p], made[p] * n_near * stack["mixed_belt_to_machine"] / near,
                        made[p] * n_hand * stack["machine_to_machine"] / ins[recipe.intermediate])
    for k, ps in row.feeds.items():
        wants = sum(need(p, capped[p])[recipe.intermediate] for p in ps)
        far = middles[k].demand(wants).ingredients[recipe.far] if wants else 0.0
        scale = min(1.0, middles[k].products[recipe.intermediate] / wants if wants else 1.0,
                    n_far * long["belt_to_machine"] / far if far else 1.0)
        for p in ps:
            capped[p] *= scale
    def room(upstream):  # products/s a P's output inserters can drop onto a lane already carrying `upstream`
        return n_out * stack["machine_to_belt"] * max(0.0, 1 - upstream / LANE)

    delivered = 0.0
    for p in sorted(row.products):
        delivered += min(capped[p], room(delivered), LANE - delivered)
    capacity = sum(made.values())

    half = rate / 2
    share = {p: half * made[p] / capacity for p in row.products}  # a P's part of its row's demand
    before = {p: sum(share[q] for q in row.products if q < p) for p in row.products}  # on the lane upstream of p
    tight_out = min(row.products, key=lambda p: room(before[p]) / share[p])
    tight_p = max(row.products, key=lambda p: made[p])  # every P has the same inserters: the busiest is tightest
    ins = need(tight_p, share[tight_p])

    def far_need(k):
        return middles[k].demand(sum(need(p, share[p])[recipe.intermediate] for p in row.feeds[k])).ingredients[recipe.far]

    k = max(row.feeds, key=far_need)
    links = (
        Link(f"near belt -> {recipe.product} plant", n_near, n_near * stack["mixed_belt_to_machine"], MARGIN,
             sum(ins[i] for i in recipe.near)),
        Link(f"{recipe.intermediate} plant -> {recipe.product} plant", n_hand, n_hand * stack["machine_to_machine"],
             MARGIN, ins[recipe.intermediate]),
        Link(f"far belt -> {recipe.intermediate} plant", n_far, n_far * long["belt_to_machine"], MARGIN,
             far_need(k)),
        Link(f"{recipe.product} plant -> output lane (the last plant's free slots)", n_out, room(before[tight_out]),
             MARGIN, share[tight_out]),
        Link("one row's plants -> its output lane", len(row.products), LANE, 1.0, half),
    )
    return Sizing(products, middles, capacity, delivered, links, 2 * delivered)


def _rate_ok(rate) -> bool:
    return not isinstance(rate, bool) and isinstance(rate, (int, float)) and 0 < rate <= 2 * LANE


def blocks(rate: float, s: Sizing) -> bool:
    """Whether a row's plants would sit blocked on output past the machine bar: they can make more than a full lane
    takes, and the rate asks for a full lane."""
    return rate / 2 >= MARGIN * LANE and s.capacity * (1 - BLOCKED_MAX) > LANE


def _layouts(rate: float, quality: str, recipe: Recipe):
    """(plants per row, east beacon) for every layout whose plants alone could pass, smallest first."""
    for n in range(1, 9):
        row = row_layout(n)
        for east in (False, True):
            s = sizing(rate, quality, recipe, row, east, *MOST)  # as many inserters as fit: the plants decide
            if s.bound >= MARGIN * rate - 1e-9 and not blocks(rate, s):
                yield n, east


def variants(request: dict) -> list[dict]:
    """Specs for `request` ({"item", "rate"}, optionally "quality") that the solver says could pass the harness:
    every plants-per-row count and east beacon whose plants make 98% of the rate without blocking on a full lane
    (the two smallest plant counts that do), and every inserter count per link whose `sizing` bound still makes
    98%. Nothing for an item this type doesn't make or a rate outside (0, 240]; an unknown quality raises SpecError."""
    item = request.get("item")
    rate = request.get("rate")
    if item not in INTERMEDIATES or not _rate_ok(rate):
        return []
    quality = request.get("quality", "legendary")
    effects.quality_level(quality)  # raises SpecError for an unknown quality
    extra = {"quality": quality} if "quality" in request else {}
    recipe = recipe_for(item)
    layouts = list(_layouts(rate, quality, recipe))
    counts = sorted({n for n, _ in layouts})[:2]
    out = []
    for n, east in layouts:
        if n not in counts:
            continue
        row = row_layout(n)
        for n_near, n_hand, n_far, n_out in itertools.product(*(range(1, high + 1) for high in MOST)):
            if sizing(rate, quality, recipe, row, east, n_near, n_hand, n_far, n_out).bound >= MARGIN * rate - 1e-9:
                out.append({"type": "plant_array", "item": item, "rate": rate, "plants_per_row": n,
                            "east_beacon": east, "near_inserters": n_near, "hand_inserters": n_hand,
                            "far_inserters": n_far, "output_inserters": n_out, **extra})
    return out


# -- check_flow ----------------------------------------------------------------------------------------------------

FLOWS = {("near belt", "product plant"), ("far belt", "intermediate plant"),
         ("intermediate plant", "product plant"), ("product plant", "output belt")}


def _belt_role(x: int, y: int) -> str | None:
    if y in (FAR_Y, mirror(FAR_Y)) and x > PORT_X + 1:
        return "far belt"
    if y in (NEAR_Y, mirror(NEAR_Y)) and x >= M_X:
        return "near belt"
    if y in (OUT_Y, OUT_B_Y) and x >= 0:
        return "output belt"
    return None


def _roles(bp) -> tuple[str | None, str | None]:
    """(product recipe, intermediate recipe): the intermediate is the recipe whose product another plant eats."""
    made = {e.recipe for e in bp.entities if e.prototype.get("type") == "assembling-machine"}
    eaten = {i["name"] for r in made if r for i in recipes.raw[r]["ingredients"]}
    middles = [r for r in made if r and any(p["name"] in eaten for p in recipes.raw[r]["results"])]
    products = [r for r in made if r not in middles]
    return (products[0] if len(products) == 1 else None), (middles[0] if len(middles) == 1 else None)


def _role(bp, pos, product, middle) -> str | None:
    for e in bp.find_entities_filtered(position=tuple(pos)):
        kind = e.prototype.get("type")
        if kind == "assembling-machine":
            return {product: "product plant", middle: "intermediate plant"}.get(e.recipe, f"a {e.recipe} plant")
        if kind == "transport-belt":
            return _belt_role(math.floor(e.position.x), math.floor(e.position.y)) or "a front-end belt"
    return None


def _where(e) -> str:
    return f"{e.name} at {tuple(e.global_position)}"


def check_flow(bp) -> list[str]:
    """Inserters move near belt -> product plant, far belt -> intermediate plant, intermediate -> product plant and
    product plant -> output belt, and every plant has each move it needs. The row belts flow east. Each near belt
    starts at a riser M fed from both sides (one near item a lane, F3) with nothing behind it; row B's M runs down
    to its near belt unbroken. Halfway along each output belt a lane reset moves the far lane onto the near lane
    (T12). Both outputs turn in past the band's end and side-load one belt from opposite sides (F3, T9)."""
    problems = []
    product, middle = _roles(bp)
    if product is None or middle is None:
        return ["the array needs exactly one product recipe and one intermediate recipe that it eats"]
    moves: dict[tuple, set] = {}
    plants = {}
    belts = {(e.tile_position.x, e.tile_position.y): e for e in bp.entities
             if e.prototype.get("type") == "transport-belt"}
    merge_x = max((x for (x, y) in belts if y == OUT_B_Y), default=None)
    for e in bp.entities:
        kind = e.prototype.get("type")
        if kind == "assembling-machine":
            plants[(e.tile_position.x, e.tile_position.y)] = e
        elif kind == "inserter":
            picks, drops = e.pickup_position, e.drop_position
            move = (_role(bp, picks, product, middle), _role(bp, drops, product, middle))
            if move not in FLOWS:
                problems.append(f"{_where(e)} moves items from {move[0] or 'nothing'} to {move[1] or 'nothing'}")
                continue
            for end, pos in (("in", drops), ("out", picks)):
                plant_role = move[1] if end == "in" else move[0]
                if plant_role.endswith("plant"):
                    target = bp.find_entities_filtered(position=tuple(pos))[0]
                    moves.setdefault((target.tile_position.x, target.tile_position.y), set()).add((end, move))
        elif kind == "transport-belt":
            at = (e.tile_position.x, e.tile_position.y)
            role = _belt_role(*at)
            if at in ((merge_x, OUT_Y), (merge_x, OUT_B_Y)):  # each output's last tile turns in to the merge
                name, facing = ("output A", SOUTH) if at[1] == OUT_Y else ("output B", NORTH)
                if e.direction != facing:
                    problems.append(f"{_where(e)} must turn {name} {facing.name.lower()} into the merge")
            elif role is not None and e.direction != EAST:
                problems.append(f"{_where(e)} on the {role} must flow east")
    needs = {product: {("in", ("near belt", "product plant")), ("in", ("intermediate plant", "product plant")),
                       ("out", ("product plant", "output belt"))},
             middle: {("in", ("far belt", "intermediate plant")), ("out", ("intermediate plant", "product plant"))}}
    for at, e in sorted(plants.items()):
        for end, (a, b) in sorted(needs.get(e.recipe, set()) - moves.get(at, set())):
            problems.append(f"{_where(e)} has no inserter moving items from {a} to {b}")

    rows = {"A": (IN_Y, NORTH, 1), "B": (M_B_Y, SOUTH, -1)}
    near = len(recipe_for(product).near) if product in INTERMEDIATES else 2
    for name, (y, up, behind) in rows.items():
        start = belts.get((M_X, y))
        if start is None or start.direction != up:
            problems.append(f"row {name}: no near-belt riser at {(M_X, y)} flowing {up.name.lower()} (the near items "
                            f"meet there)")
            continue
        back = belts.get((M_X, y + behind))
        if back is not None and back.direction == up:
            problems.append(f"row {name}: a belt feeds the riser at {(M_X, y)} from behind, so a near item would "
                            f"cover both lanes")
        feeders = [(M_X - 1, EAST), (M_X + 1, WEST)][:near]
        for x, facing in feeders:
            f = belts.get((x, y))
            if f is None or f.direction != facing:
                problems.append(f"row {name}: no belt at {(x, y)} side-loading the riser from the "
                                f"{'west' if facing == EAST else 'east'} (F3): each near item needs its own lane")

    for y in range(M_B_Y + 1, mirror(NEAR_Y)):
        b = belts.get((M_X, y))
        if b is None or b.direction != SOUTH:
            problems.append(f"row B: no belt at {(M_X, y)} flowing south from its riser to its near belt")

    # the lane reset (T12): a splitter on each output belt after half the row's P, prioritising its near-side half,
    # which turns back onto the output belt's near lane
    row_ps = sorted(x for (x, y), e in plants.items() if y == ROW_Y and e.recipe == product)
    h = len(row_ps) // 2
    splitters = [e for e in bp.entities if e.name == SPLITTER and e.direction == EAST]
    for name, (sy, oy, priority, side_y, facing) in {
            "A": (OUT_IN_Y, OUT_Y, "left", OUT_IN_Y, SOUTH),
            "B": (OUT_B_Y, OUT_B_Y, "right", mirror(OUT_IN_Y), NORTH)}.items():
        found = [e for e in splitters if e.tile_position.y == sy and e.tile_position.x >= 0]
        if h == 0:
            continue
        if len(found) != 1:
            problems.append(f"row {name}: {len(found)} lane reset splitters on its output belt at y={oy}, not 1 "
                            f"(T12): without one, its last plants find the far lane full")
            continue
        (sp,) = found
        x = sp.tile_position.x
        if sp.output_priority != priority:
            problems.append(f"row {name}: the lane reset {_where(sp)} must prioritise its inserter-side output "
                            f"(output_priority={priority!r}), got {sp.output_priority!r}")
        side = belts.get((x + 1, side_y))
        if side is None or side.direction != facing:
            problems.append(f"row {name}: no belt at {(x + 1, side_y)} flowing {facing.name.lower()} to side-load the "
                            f"lane reset's priority half onto the near lane (T12)")
        upstream = sum(1 for px in row_ps if px + PLANT_SIZE <= x + 1)
        if upstream != h:
            problems.append(f"row {name}: the lane reset at x={x} comes after {upstream} plants, not half the row ({h})")

    if merge_x is not None:
        mid = belts.get((merge_x, MERGE_Y))
        if mid is None or mid.direction != EAST:
            problems.append(f"no belt at {(merge_x, MERGE_Y)} flowing east for both outputs to side-load (T9)")
        for y, name, facing in ((MERGE_Y - 1, "output A", SOUTH), (MERGE_Y + 1, "output B", NORTH)):
            b = belts.get((merge_x, y))
            if b is None or b.direction != facing:
                problems.append(f"no belt at {(merge_x, y)} bringing {name} {facing.name.lower()} into the merge: "
                                f"without both, the merge tile curves and one row's lane is lost (T9)")
    return problems


# -- the generator -------------------------------------------------------------------------------------------------

@register("plant_array", checks=(check_flow,), variants=variants, research="all")
def plant_array(spec: dict) -> tuple[list, list[str], list[Port]]:
    recipe = recipe_for(spec.get("item", "advanced-circuit"))
    rate = spec.get("rate", 2 * LANE)
    if not _rate_ok(rate):
        raise SpecError(f"'rate' must be a number of {recipe.product}/s above 0 and at most {2 * LANE:g} (a stacked "
                        f"{BELT}), got {rate!r}")
    quality = spec.get("quality", "legendary")
    effects.quality_level(quality)  # raises SpecError for an unknown quality
    smallest = next(_layouts(rate, quality, recipe), (1, True))  # nothing passes: the smallest, with its WARNINGs
    n = count(spec, "plants_per_row", smallest[0], 1, 8)
    east = spec.get("east_beacon", smallest[1] if n == smallest[0] else True)
    if not isinstance(east, bool):
        raise SpecError(f"'east_beacon' must be true or false, got {east!r}")
    row = row_layout(n)

    # each link's default: the fewest inserters that carry its demand with the harness's margin, by `sizing`
    picked = list(MOST)
    for i, (key, high) in enumerate(COUNTS):
        for k in range(1, high + 1):
            link = sizing(rate, quality, recipe, row, east, *picked[:i], k, *picked[i + 1:]).links[i]
            if link.carries * MARGIN >= link.demand - 1e-9:
                break
        picked[i] = count(spec, key, k, 1, high)
    n_near, n_hand, n_far, n_out = picked
    s = sizing(rate, quality, recipe, row, east, *picked)

    out: list = []

    def add(name, x, y, height=1, direction=None, both=True, **kw):
        """Place an entity in row A's coordinates and, with `both`, its mirror image in row B."""
        for my, d in ((y, direction),) + (((mirror(y, height), _flip(direction)),) if both else ()):
            if d is not None:
                kw["direction"] = d
            out.append(new_entity(name, tile_position=(x, my), **kw))

    def belt(x, y, d, both=False):
        add(BELT, x, y, direction=d, both=both)

    def underground(x, y, d, io):
        out.append(new_entity(UNDERGROUND, tile_position=(x, y), direction=d, io_type=io))

    # plants, beacons and poles
    for p in row.products:
        add(PLANT, p, ROW_Y, PLANT_SIZE, recipe=recipe.product, quality=quality)
    for k in row.intermediates:
        add(PLANT, k, ROW_Y, PLANT_SIZE, recipe=recipe.intermediate, quality=quality)
    for x in band(row):
        add(BEACON, x, BAND_Y, BEACON_SIZE, both=False, quality=quality)
    if east:
        add(BEACON, row.end, ROW_Y, BEACON_SIZE, quality=quality)
    for e in out:
        modules(e, PROD if e.name == PLANT else SPEED, quality)
    poles = pole_columns(row)
    for x in poles:
        add(POLE, x, IN_Y)
        add(POLE, x, OUT_IN_Y)

    # inserters: near belt -> P, far belt -> K (long-handed), K -> P across each gap, P -> output belt
    near_xs, far_xs, out_xs = [], [], []
    for p in row.products:
        cols = inserter_columns(p, poles)
        near_xs += cols[:n_near]
        out_xs += cols[-n_out:]
    for k in row.intermediates:
        far_xs += inserter_columns(k, poles)[:n_far]
    for x in near_xs:
        add(INSERTER, x, IN_Y, direction=NORTH, quality=quality)
    for x in far_xs:
        add(LONG, x, IN_Y, direction=NORTH, quality=quality)
    for x in out_xs:
        add(INSERTER, x, OUT_IN_Y, direction=NORTH, quality=quality)
    for g, k, _ in row.gaps:
        for y in range(ROW_Y, ROW_Y + n_hand):
            add(INSERTER, g, y, direction=EAST if k > g else WEST, quality=quality)

    # row belts: each starts where the front end hands over and ends at its last inserter (no idle belt, T5)
    merge_x = max(row.end + 3, band(row)[-1] + BEACON_SIZE)
    for x in range(PORT_X + 2, max(far_xs) + 1):
        belt(x, FAR_Y, EAST, both=True)
    for x in range(M_X + 1, max(near_xs) + 1):
        belt(x, NEAR_Y, EAST, both=True)
    # the lane reset (T12, the user's, 2026-10-12): halfway along each output belt a splitter sends the far lane's
    # items out its near-side half, which turns back and side-loads them onto the near lane, so the far lane is
    # empty again for the row's last plants
    rx = reset_column(row, poles, n_out)
    for x in range(min(out_xs), merge_x):
        if x != rx:
            belt(x, OUT_Y, EAST)
            belt(x, OUT_B_Y, EAST)
    if rx is not None:
        out.append(new_entity(SPLITTER, tile_position=(rx, OUT_IN_Y), direction=EAST, output_priority="left"))
        out.append(new_entity(SPLITTER, tile_position=(rx, OUT_B_Y), direction=EAST, output_priority="right"))
        add(BELT, rx + 1, OUT_IN_Y, direction=SOUTH)  # and its mirror image, flowing north

    # the east merge (T9): past the band's end both outputs turn in and side-load one belt from opposite sides
    for y in range(OUT_Y, MERGE_Y):
        belt(merge_x, y, SOUTH)
    for y in range(MERGE_Y + 1, OUT_B_Y + 1):
        belt(merge_x, y, NORTH)
    belt(merge_x, MERGE_Y, EAST)

    # the west front end (see the module docstring): risers M where the near items meet, then each row's near belt.
    # Row A's M is at the top of the front end; row B's as soon as its near items surface from under the band, so
    # one belt runs down to row B's near belt instead of one per item (the user's in-game copy, 2026-10-12).
    belt(M_X, IN_Y, NORTH)
    belt(M_X, M_B_Y, SOUTH)
    for y in range(M_B_Y + 1, mirror(NEAR_Y)):
        belt(M_X, y, SOUTH)
    add(BELT, M_X, NEAR_Y, direction=EAST)
    two = len(recipe.near) == 2
    g_y, p_y = 0, 3  # the near items' rows
    # the far item: split at the top; row A's far belt runs on east, row B's comes down x=-6, hopping under the near
    # items' belts in one go (the user's in-game copy, 2026-10-12)
    fx = PORT_X + 2
    belt(PORT_X, FAR_Y, EAST)
    out.append(new_entity(SPLITTER, tile_position=(PORT_X + 1, FAR_Y), direction=EAST))
    hop_out = (p_y if two else g_y) + 1
    belt(fx, FAR_Y + 1, SOUTH)
    underground(fx, g_y - 1, SOUTH, "input")
    underground(fx, hop_out, SOUTH, "output")
    for y in range(hop_out + 1, mirror(FAR_Y)):
        belt(fx, y, SOUTH)
    # the first near item: straight over the far item's hop, split at x=-4; up and down x=-3 to the west side of
    # each M
    for x in range(PORT_X, PORT_X + 4):
        belt(x, g_y, EAST)
    out.append(new_entity(SPLITTER, tile_position=(PORT_X + 4, g_y), direction=EAST))
    gx = M_X - 1
    belt(gx, g_y, NORTH)
    belt(gx, IN_Y, EAST)
    belt(gx, g_y + 1, SOUTH)
    if two:  # hop the second item's belt at (gx, p_y)
        underground(gx, p_y - 1, SOUTH, "input")
        underground(gx, p_y + 1, SOUTH, "output")
    else:
        for y in range(g_y + 2, BAND_Y - 1):
            belt(gx, y, SOUTH)
    belt(gx, M_B_Y, EAST)
    risers = (gx, M_X + 1) if two else (gx,)
    for x in risers:  # the risers pass under the band's west beacon
        underground(x, BAND_Y - 1, SOUTH, "input")
        underground(x, mirror(BAND_Y - 1), SOUTH, "output")
    if two:
        # the second near item: straight over both hops, split at x=-2; up and down x=-1 to the east side of each M
        px = M_X + 1
        for x in range(PORT_X, M_X):
            belt(x, p_y, EAST)
        out.append(new_entity(SPLITTER, tile_position=(M_X, p_y), direction=EAST))
        for y in range(IN_Y + 1, p_y + 1):
            belt(px, y, NORTH)
        belt(px, IN_Y, WEST)
        belt(px, p_y + 1, SOUTH)
        belt(px, M_B_Y, WEST)

    notes = _notes(rate, recipe, row, east, s, quality)
    wants = block_inputs(rate, quality, recipe)
    ports = [
        Port("input", recipe.far, BELT, (PORT_X, FAR_Y), int(EAST), wants[recipe.far], STACK),
        Port("input", recipe.near[0], BELT, (PORT_X, g_y), int(EAST), wants[recipe.near[0]], STACK),
        *([Port("input", recipe.near[1], BELT, (PORT_X, p_y), int(EAST), wants[recipe.near[1]], STACK)]
          if len(recipe.near) == 2 else []),
        Port("output", recipe.product, BELT, (merge_x, MERGE_Y), int(EAST), float(rate), STACK),
    ]
    return out, notes, ports


def block_inputs(rate: float, quality: str, recipe: Recipe) -> dict[str, float]:
    """Items/s of each input the block eats at `rate` (beacons change speed, not productivity)."""
    product = plant(recipe.product, quality, 0).demand(rate).ingredients
    middle = plant(recipe.intermediate, quality, 0).demand(product[recipe.intermediate]).ingredients
    return {**{i: product[i] for i in recipe.near}, recipe.far: middle[recipe.far]}


def _flip(d):
    return {NORTH: SOUTH, SOUTH: NORTH}.get(d, d)


def _notes(rate, recipe, row, east, s: Sizing, quality) -> list[str]:
    p_beacons, k_beacons = beacon_counts(row, east)
    made = {p: m.products[recipe.product] for p, m in s.products.items()}
    cable = {k: m.products[recipe.intermediate] for k, m in s.intermediates.items()}
    notes = [
        f"{len(row.products)} {recipe.product} plants and {len(row.intermediates)} {recipe.intermediate} plants per "
        f"row, 2 rows",
        "beacons per product plant, west to east: " + ", ".join(str(p_beacons[p]) for p in row.products)
        + f"; each row can make {s.capacity:.2f}/s and delivers {s.row:.2f}/s ({rate / 2:g}/s wanted)",
        f"{recipe.intermediate} plants make at least {min(cable.values()):.2f}/s each",
    ]
    if 2 * s.row < rate - 1e-9:
        notes.append(f"WARNING: the block delivers {2 * s.row:.2f}/s, under the {rate:g}/s target")
    if blocks(rate, s):
        notes.append(f"WARNING: a row can make {s.capacity:.2f}/s against a full lane's {LANE:g}/s, so its plants "
                     f"would sit blocked on output past the machine bar ({BLOCKED_MAX:.0%})")
    for link in s.links:
        kind = "long-handed" if link.name.startswith("far") else "stack"
        notes.append(f"{link.name}: {link.inserters} {kind} inserter(s) carry {link.carries:.2f}/s for "
                     f"{link.demand:.2f}/s")
        if link.carries * link.margin < link.demand - 1e-9:
            notes.append(f"WARNING: {link.name} carries {link.carries:.2f}/s, under {link.demand:.2f}/s"
                         + (f" with the harness's {MARGIN:.0%} margin" if link.margin < 1 else ""))
    if quality != "legendary":
        notes.append(f"inserter rates are measured for legendary inserters only; at {quality} the harness decides")
    notes.append("the harness runs this type with all research (registered research=\"all\"): stacking items on belts "
                 "and the inserters' hand sizes need it")
    return notes
