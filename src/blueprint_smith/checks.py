"""Static structural checks run on every built blueprint. These are the 'guaranteed' tier:
they prove wiring/power/footprint facts, not real throughput."""
from draftsman.blueprintable import Blueprint


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
    """Every electric consumer must overlap the supply area of at least one pole."""
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
            pw, ph = p.tile_width / 2, p.tile_height / 2
            if abs(ex - px) < hw + pw + d - 1e-6 and abs(ey - py) < hh + ph + d - 1e-6:
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


ALL_CHECKS = (inserter_wiring, power_coverage, pole_network)
