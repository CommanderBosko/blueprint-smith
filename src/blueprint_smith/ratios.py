"""Throughput math from real prototype data (no modules/beacons yet)."""
import math

from draftsman.data import entities, recipes

from .errors import SpecError


def recipe_info(recipe_name: str) -> dict:
    r = recipes.raw.get(recipe_name) if isinstance(recipe_name, str) else None
    if r is None:
        raise SpecError(f"unknown recipe {recipe_name!r}")
    products = r.get("results") or []
    amount = next((p.get("amount", 1) for p in products if p.get("name") == recipe_name), 1)
    return {
        "time": r.get("energy_required", 0.5),
        "amount": amount,
        "ingredients": r.get("ingredients", []),
        "category": r.get("category", "crafting"),
    }


def _crafts(machine: str, recipe_name: str) -> tuple[float, dict]:
    """Recipe completions per second for one `machine` (base crafting speed), plus the recipe's info."""
    proto = entities.raw.get(machine) if isinstance(machine, str) else None
    if proto is None or "crafting_speed" not in proto:
        raise SpecError(f"unknown crafting machine {machine!r}")
    info = recipe_info(recipe_name)
    categories = proto.get("crafting_categories", [])
    if info["category"] not in categories:
        raise SpecError(
            f"{machine} can't craft {recipe_name!r} (category {info['category']!r}; it crafts {', '.join(categories)})"
        )
    return proto["crafting_speed"] / info["time"], info


def crafts_per_second(machine: str, recipe_name: str) -> float:
    """Items of `recipe_name` one `machine` produces per second (base crafting speed)."""
    crafts, info = _crafts(machine, recipe_name)
    return crafts * info["amount"]


def ingredients_per_second(machine: str, recipe_name: str) -> dict[str, float]:
    """Item ingredients one `machine` consumes per second (base crafting speed). Fluids don't ride belts."""
    crafts, info = _crafts(machine, recipe_name)
    return {i["name"]: crafts * i.get("amount", 1) for i in info["ingredients"] if i.get("type", "item") == "item"}


def machines_for_rate(machine: str, recipe_name: str, items_per_second: float) -> int:
    return max(1, math.ceil(items_per_second / crafts_per_second(machine, recipe_name) - 1e-9))


def belt_lane_capacity(belt: str) -> float:
    """Items/second one lane of `belt` carries (belt speed is tiles/tick; 8 items per tile per 2 lanes)."""
    return entities.raw[belt]["speed"] * 60 * 4
