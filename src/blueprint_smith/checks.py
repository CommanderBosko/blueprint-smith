"""Static structural checks run on every built blueprint. These are the 'guaranteed' tier:
they prove wiring/power/footprint facts, not real throughput."""
from functools import cache

from draftsman.blueprintable import Blueprint
from draftsman.classes.entity import Entity
from draftsman.constants import InventoryType
from draftsman.data import entities, items, modules, recipes


def inserter_wiring(bp: Blueprint) -> list[str]:
    """Every inserter must pick up from and drop onto some entity."""
    problems = []
    for e in bp.entities:
        if e.prototype.get("type") != "inserter":
            continue
        for label, pos in (("pickup", e.pickup_position), ("drop", e.drop_position)):
            if not bp.find_entities_filtered(position=tuple(pos)):
                problems.append(f"{e.name} at {tuple(e.global_position)} has nothing at its {label} position {tuple(pos)}")
    return problems


def _electric(e) -> bool:
    src = e.prototype.get("energy_source")
    return isinstance(src, dict) and src.get("type") == "electric"


def power_coverage(bp: Blueprint) -> list[str]:
    """Every electric consumer must overlap the supply area of at least one pole.
    The supply area reaches `supply_area_distance` from the pole's centre, not its edge:
    a medium pole (3.5) supplies 7x7, a big pole (2x2, distance 2) only 4x4."""
    poles = [e for e in bp.entities if e.prototype.get("type") == "electric-pole"]
    problems = []
    for e in bp.entities:
        if not _electric(e):
            continue
        ex, ey = e.global_position
        hw, hh = e.tile_width / 2, e.tile_height / 2
        covered = False
        for p in poles:
            d = p.prototype.get("supply_area_distance", 0)
            px, py = p.global_position
            if abs(ex - px) < hw + d - 1e-6 and abs(ey - py) < hh + d - 1e-6:
                covered = True
                break
        if not covered:
            problems.append(f"{e.name} at {(ex, ey)} is not covered by any electric pole")
    return problems


COPPER = 5  # defines.wire_connector_id.pole_copper


def pole_network(bp: Blueprint) -> list[str]:
    """Poles must be copper-wired into one network, each wire within both poles' reach.
    A pasted blueprint only has the wires it carries, so unwired poles stay dead in-game."""
    poles = [e for e in bp.entities if e.prototype.get("type") == "electric-pole"]
    parent = {id(p): id(p) for p in poles}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    problems = []
    for a, ca, b, cb in bp.wires:
        a, b = a(), b()
        if COPPER not in (ca, cb) or id(a) not in parent or id(b) not in parent:
            continue
        (ax, ay), (bx, by) = a.global_position, b.global_position
        span = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        reach = min(a.prototype.get("maximum_wire_distance", 0), b.prototype.get("maximum_wire_distance", 0))
        if span > reach + 1e-6:
            problems.append(f"wire {a.name} {(ax, ay)} -> {b.name} {(bx, by)} spans {span:.2f}, reach is {reach}")
        parent[root(id(a))] = root(id(b))
    groups: dict[int, list] = {}
    for p in poles:
        groups.setdefault(root(id(p)), []).append(p)
    if len(groups) > 1:
        main = max(groups, key=lambda k: len(groups[k]))
        for p in poles:
            if root(id(p)) != main:
                problems.append(f"{p.name} at {tuple(p.global_position)} is not wired to the main pole network")
    return problems


# the inventory (defines.inventory) each entity type takes module requests into
MODULE_INVENTORY = {
    "assembling-machine": InventoryType.ASSEMBLING_MACHINE_MODULES,
    "furnace": InventoryType.FURNACE_MODULES,
    "rocket-silo": InventoryType.ROCKET_SILO_MODULES,
    "mining-drill": InventoryType.MINING_DRILL_MODULES,
    "lab": InventoryType.LAB_MODULES,
    "beacon": InventoryType.BEACON_MODULES,
}
ALL_EFFECTS = frozenset({"consumption", "speed", "productivity", "pollution", "quality"})
# allowed_effects when a prototype leaves it out (prototype API docs); beacons and crafting machines allow none
DEFAULT_ALLOWED_EFFECTS = {"mining-drill": ALL_EFFECTS, "lab": ALL_EFFECTS - {"quality"}}


def _where(e) -> str:
    return f"{e.name} at {tuple(e.global_position)}"


def _module_requests(e) -> list[tuple[int, str, str, int]]:
    """(slot, item, quality, count) for each item request into `e`'s module inventory."""
    inv = MODULE_INVENTORY.get(e.prototype.get("type"))
    return [
        (pos.stack, req.id.name, req.id.quality, pos.count)
        for req in e.item_requests
        for pos in req.items.in_inventory
        if inv is not None and pos.inventory == inv
    ]


def module_items(e) -> list[tuple[str, str]]:
    """(item, quality) per module `e` requests into its module slots, in slot order. Draftsman keeps them in
    `item_requests`: insert plans keyed by item name and quality, each listing (inventory, slot, count)."""
    return [(name, q) for _, name, q, count in sorted(_module_requests(e)) for _ in range(count)]


def _allowed_effects(proto: dict) -> frozenset:
    allowed = proto.get("allowed_effects", DEFAULT_ALLOWED_EFFECTS.get(proto.get("type"), ()))
    return frozenset([allowed] if isinstance(allowed, str) else allowed)


def _recipe_allowed_effects(recipe: dict) -> frozenset:
    flags = {"consumption": True, "speed": True, "productivity": False, "pollution": True, "quality": True}
    return frozenset(k for k, default in flags.items() if recipe.get(f"allow_{k}", default))


def _bonuses(module: dict) -> frozenset:
    """The effects a module raises. 2.0 only restricts these: a speed module (-quality) still goes into a beacon,
    which doesn't allow quality."""
    return frozenset(k for k, v in module.get("effect", {}).items() if v > 0)


def module_validity(bp: Blueprint) -> list[str]:
    """Module requests must be ones the game accepts: no more than the prototype's `module_slots` (quality adds
    none in 2.0.77), each in a slot that exists, only modules, every module's bonuses in the entity's
    `allowed_effects` and its category in `allowed_module_categories` (when given), and the same for the recipe
    set on a crafting machine (`allow_productivity` defaults to false). Beacons don't allow productivity."""
    problems = []
    for e in bp.entities:
        held = _module_requests(e)
        if not held:
            continue
        slots = e.prototype.get("module_slots", 0)
        count = sum(n for *_, n in held)
        if count > slots:
            problems.append(f"{_where(e)} requests {count} modules into {slots} module slots")
        else:
            taken = [s for s, *_, n in held for _ in range(n)]
            for s in sorted(set(taken)):
                if s >= slots:
                    problems.append(f"{_where(e)} requests module slot {s}, but its slots are 0-{slots - 1}")
                elif taken.count(s) > 1:
                    problems.append(f"{_where(e)} requests module slot {s} {taken.count(s)} times")
        recipe = recipes.raw.get(getattr(e, "recipe", None) or "")
        for name in dict.fromkeys(name for _, name, _, _ in held):
            module = modules.raw.get(name)
            if module is None:
                problems.append(f"{_where(e)} requests {name} into its module slots, but it isn't a module")
                continue
            limits = [(e.prototype, _allowed_effects(e.prototype), "")]
            if recipe is not None:
                limits.append((recipe, _recipe_allowed_effects(recipe), f" with recipe {e.recipe}"))
            for proto, allowed, context in limits:
                if banned := _bonuses(module) - allowed:
                    problems.append(f"{_where(e)} can't take {name}{context}: {', '.join(sorted(banned))} not allowed")
                categories = proto.get("allowed_module_categories")
                if categories is not None and module.get("category") not in categories:
                    problems.append(f"{_where(e)} can't take {name}{context}: category {module.get('category')} not allowed")
    return problems


RECEIVER_TYPES = ("assembling-machine", "furnace", "rocket-silo", "mining-drill", "lab")


def _receives_beacons(e) -> bool:
    p = e.prototype
    return (
        p.get("type") in RECEIVER_TYPES
        and (p.get("effect_receiver") or {}).get("uses_beacon_effects", True)
        and bool(_allowed_effects(p))
    )


def beacon_targets(bp: Blueprint) -> dict[Entity, list[Entity]]:
    """{machine: [beacons reaching it]} for every entity that takes beacon effects, in blueprint order, including
    machines no beacon reaches (an empty list); each list is in blueprint order too. Keys and values are the
    blueprint's own entities; read a beacon's modules and quality with `module_items` and `.quality`.

    Takes beacon effects: a crafting machine, mining drill or lab whose `effect_receiver` doesn't turn off
    `uses_beacon_effects` and which allows some effect (so not assembling machine 1, stone/steel furnaces or the
    burner drill). A beacon supplies its tile footprint grown by `supply_area_distance` on every side (3x3,
    reach 3: 9x9), and reaches a machine whose collision box overlaps that square. Collision boxes sit less than
    half a tile inside their tiles, so in practice a machine is reached when one of its tiles is in the square:
    up to 2 tiles of gap between a beacon and the machine. Quality doesn't change the reach in 2.0.77."""
    beacons = []
    for b in bp.entities:
        if b.prototype.get("type") == "beacon":
            d = b.prototype.get("supply_area_distance", 0)
            x, y = b.tile_position.x, b.tile_position.y
            beacons.append((b, (x - d, y - d, x + b.tile_width + d, y + b.tile_height + d)))
    targets = {}
    for m in bp.entities:
        if not _receives_beacons(m):
            continue
        box = m.get_world_bounding_box()
        (mx1, my1), (mx2, my2) = box.top_left, box.bot_right
        targets[m] = [
            b for b, (ax1, ay1, ax2, ay2) in beacons
            if mx1 < ax2 - 1e-6 and ax1 + 1e-6 < mx2 and my1 < ay2 - 1e-6 and ay1 + 1e-6 < my2
        ]
    return targets


def beacon_reach(bp: Blueprint) -> list[str]:
    """Every beacon must reach at least one machine that takes beacon effects (see `beacon_targets`)."""
    reached = {b for bs in beacon_targets(bp).values() for b in bs}
    return [
        f"{_where(b)} reaches no machine that takes beacon effects"
        for b in bp.entities
        if b.prototype.get("type") == "beacon" and b not in reached
    ]


# underground direction (N=0 E=4 S=8 W=12) -> one tile along it
STEP = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}


def underground_pairing(bp: Blueprint) -> list[str]:
    """Every underground belt must pair the way the game pairs it. An entrance takes the first underground of its
    own name it meets along its direction within `max_distance` tiles (entrance to exit: yellow 5, red 7, blue 9,
    turbo 11); perpendicular ones and other tiers are passed under. That first one must be an exit facing the same
    way: an entrance, or either kind facing back, blocks it. An exit looks back for its entrance the same way.
    Draftsman's `direction` is the flow direction for both kinds."""
    ugs = [e for e in bp.entities if e.prototype.get("type") == "underground-belt"]
    at = {(e.name, e.tile_position.x, e.tile_position.y): e for e in ugs}
    problems = []
    for e in ugs:
        d, entry = int(e.direction), e.io_type == "input"
        sx, sy = STEP[d] if entry else (-STEP[d][0], -STEP[d][1])
        reach = e.prototype.get("max_distance", 0)
        kind, partner = ("entrance", "exit") if entry else ("exit", "entrance")
        found = None
        for k in range(1, reach + 1):
            o = at.get((e.name, e.tile_position.x + k * sx, e.tile_position.y + k * sy))
            if o is not None and int(o.direction) in (d, (d + 8) % 16):
                found = o
                break
        if found is None:
            problems.append(f"{e.name} {kind} at {tuple(e.global_position)} has no {partner} within {reach} tiles")
        elif int(found.direction) != d or found.io_type == e.io_type:
            other = "entrance" if found.io_type == "input" else "exit"
            problems.append(
                f"{e.name} {kind} at {tuple(e.global_position)} is blocked by the {other} "
                f"facing {int(found.direction)} at {tuple(found.global_position)}"
            )
    return problems


@cache
def _placed_by() -> dict[str, frozenset]:
    """entity name -> the items that place it: items whose `place_result` it is, plus the entity's `placeable_by`."""
    out: dict[str, set] = {}
    for name, item in items.raw.items():
        if item.get("place_result"):
            out.setdefault(item["place_result"], set()).add(name)
    for name, proto in entities.raw.items():
        by = proto.get("placeable_by")
        for p in [by] if isinstance(by, dict) else by or ():
            out.setdefault(name, set()).add(p["item"])
    return {k: frozenset(v) for k, v in out.items()}


def hidden_entities(bp: Blueprint) -> list[str]:
    """Every entity must be buildable in survival: the prototype isn't hidden and some item that isn't hidden
    places it. 2.0.77 marks the loaders (turbo included), loader-1x1, the infinity, linked and bottomless chests
    and the energy interfaces through their items' `hidden`, which the game carries over to the entity."""
    problems = []
    for e in bp.entities:
        proto = entities.raw.get(e.name)
        if proto is None:
            continue  # unknown entities already fail as draftsman warnings
        visible = [i for i in _placed_by().get(e.name, ()) if i in items.raw and not items.raw[i].get("hidden")]
        if proto.get("hidden") or not visible:
            problems.append(f"{_where(e)} is hidden: no item a player can get places it")
    return problems


ALL_CHECKS = (
    inserter_wiring,
    power_coverage,
    pole_network,
    module_validity,
    beacon_reach,
    underground_pairing,
    hidden_entities,
)
