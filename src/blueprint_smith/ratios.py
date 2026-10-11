"""Throughput math from real prototype data (no modules/beacons yet)."""
import math

from draftsman.data import entities, recipes

from .errors import SpecError


def recipe_info(recipe_name: str) -> dict:
    try:
        r = recipes.raw[recipe_name]
    except KeyError:
        raise SpecError(f"unknown recipe {recipe_name!r}") from None
    products = r.get("results") or []
    amount = next((p.get("amount", 1) for p in products if p.get("name") == recipe_name), 1)
    return {"time": r.get("energy_required", 0.5), "amount": amount, "ingredients": r.get("ingredients", [])}


def crafts_per_second(machine: str, recipe_name: str) -> float:
    """Items of `recipe_name` one `machine` produces per second (base crafting speed)."""
    try:
        speed = entities.raw[machine]["crafting_speed"]
    except KeyError:
        raise SpecError(f"unknown crafting machine {machine!r}") from None
    info = recipe_info(recipe_name)
    return speed / info["time"] * info["amount"]


def machines_for_rate(machine: str, recipe_name: str, items_per_second: float) -> int:
    return max(1, math.ceil(items_per_second / crafts_per_second(machine, recipe_name) - 1e-9))


def belt_lane_capacity(belt: str) -> float:
    """Items/second one lane of `belt` carries (belt speed is tiles/tick; 8 items per tile per 2 lanes)."""
    return entities.raw[belt]["speed"] * 60 * 4
