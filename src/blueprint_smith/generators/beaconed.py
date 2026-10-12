"""Building blocks shared by the beaconed M2 generators (`circuit_block`, `plant_array`): the standard meta's
entities, the stacked turbo belt, spec counts, and the solver's rates for one plant under N shared beacons."""
from dataclasses import dataclass

from draftsman.data import entities

from .. import effects, ratios
from ..errors import SpecError

PLANT, BEACON, BELT, INSERTER = "electromagnetic-plant", "beacon", "turbo-transport-belt", "stack-inserter"
PROD, SPEED = "productivity-module-3", "speed-module-3"
STACK = 4  # items per belt slot once belt stacking is researched
MARGIN = 0.98  # the harness's output bar
LANE = ratios.belt_lane_capacity(BELT) * STACK  # 120/s on a stacked turbo lane


def count(spec: dict, key: str, default: int, low: int = 1, high: int = 4) -> int:
    n = spec.get(key, default)
    if isinstance(n, bool) or not isinstance(n, int) or not low <= n <= high:
        raise SpecError(f"'{key}' must be an integer from {low} to {high}, got {n!r}")
    return n


def plant(recipe: str, quality: str, beacons: int) -> effects.MachineRates:
    """An EM plant on `recipe` with productivity-3 in every slot, under `beacons` beacons full of speed-3, all at
    `quality`, with everything researched."""
    slots = entities.raw[PLANT]["module_slots"]
    beacon = effects.Beacon(((SPEED, quality),) * entities.raw[BEACON]["module_slots"], quality)
    return effects.machine_rates(PLANT, recipe, quality=quality, modules=[(PROD, quality)] * slots,
                                 beacons=[beacon] * beacons, research="all")


def modules(e, module: str, quality: str):
    """Fill every module slot of a plant or beacon with `module` at `quality`."""
    e.request_modules(module, range(entities.raw[e.name]["module_slots"]), quality=quality)
    return e


@dataclass(frozen=True)
class Link:
    name: str
    inserters: int
    carries: float  # items/s the link's inserters move, or a full lane's 120/s
    margin: float  # what its WARNING applies: the harness's 98% while inserters are the limit, 1 for a full lane
    demand: float  # items/s the link must move for the block's rate
