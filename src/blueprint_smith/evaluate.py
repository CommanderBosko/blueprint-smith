"""Run a built blueprint in the headless harness and judge it (v2, amended P2).

The verdict is a hard pass/fail: output below 98% of target fails, and so does any machine blocked on output for
more than 5% of the window (unless it unloads only into other machines), or whose output backs up. A machine
idle for want of ingredients or power only shows in the reported utilisation (harness/verdict.py).
"""
import math
from dataclasses import dataclass

from draftsman.data import entities, recipes

from . import harness
from .pipeline import BuildResult

TICKS = 60
MIN_WARMUP = 2 * 60 * TICKS
MIN_WINDOW = 60 * TICKS
# Furnaces fed together craft in step, so output comes in bursts: span 10 of the slowest craft cycle.
CYCLES = 10
# Items must ride the whole layout before the output settles.
TRANSITS = 3


@dataclass
class Evaluation:
    verdict: harness.Verdict
    result: harness.HarnessResult
    warmup_ticks: int
    window_ticks: int


def _item_ingredients(recipe: dict) -> set[str]:
    return {i["name"] for i in recipe.get("ingredients", []) if i.get("type", "item") == "item"}


def craft_cycle(bp, ports) -> float:
    """Seconds per craft of the slowest machine (base crafting speed).

    Furnaces carry no recipe in a blueprint, so a furnace counts every recipe it could reach from the input ports:
    iron ore makes plates, and those plates could make steel.
    """
    reachable = {p.item for p in ports if p.role == "input"}
    slowest = 0.0
    for e in bp.entities:
        proto = entities.raw.get(e.name, {})
        speed = proto.get("crafting_speed")
        if not speed:
            continue
        categories = proto.get("crafting_categories", [])
        names = [e.recipe] if getattr(e, "recipe", None) else _reachable(categories, reachable)
        for name in names:
            slowest = max(slowest, recipes.raw[name].get("energy_required", 0.5) / speed)
    return slowest


def _reachable(categories: list[str], items: set[str]) -> list[str]:
    items, found = set(items), []
    while True:
        new = [name for name, r in recipes.raw.items()
               if name not in found and r.get("category", "crafting") in categories
               and _item_ingredients(r) and _item_ingredients(r) <= items]
        if not new:
            return found
        found += new
        items |= {p["name"] for name in new for p in recipes.raw[name].get("results", [])}


def timing(bp, ports) -> tuple[int, int]:
    """(warmup, window) in ticks: long enough for items to cross the layout and for craft bursts to average out."""
    cycle = craft_cycle(bp, ports) * TICKS
    tiles = [e.tile_position for e in bp.entities]
    path = (max(t.x for t in tiles) - min(t.x for t in tiles) + 1) + (max(t.y for t in tiles) - min(t.y for t in tiles) + 1)
    speeds = [entities.raw[p.belt]["speed"] for p in ports]  # tiles per tick
    transit = path / min(speeds) if speeds else 0
    warmup = max(MIN_WARMUP, TRANSITS * transit, CYCLES * cycle)
    window = max(MIN_WINDOW, CYCLES * cycle)
    return math.ceil(warmup), math.ceil(window)


def evaluate(built: BuildResult, **run_options) -> Evaluation:
    """Run `built` headless and judge it. `run_options` go to harness.run (research, keep_dir, ...).
    Raises harness.HarnessUnavailable / harness.HarnessError if it can't run."""
    warmup, window = timing(built.blueprint, built.ports)
    result = harness.run(built.string, built.ports, warmup_ticks=warmup, window_ticks=window, **run_options)
    return Evaluation(harness.judge(result), result, warmup, window)
