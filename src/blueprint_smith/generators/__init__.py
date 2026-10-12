"""Generator registry. A generator takes a spec dict and returns (entities, notes, ports)."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..errors import SpecError


@dataclass(frozen=True)
class Port:
    """Where items enter or leave a blueprint, so the harness knows where to feed and measure it.
    Generators give `tile` in their own tile coordinates; `pipeline.build` makes it relative to the
    blueprint's top-left tile (the minimum tile_position over all entities)."""

    role: str  # "input" | "output"
    item: str  # e.g. "iron-ore"
    belt: str  # belt prototype at the port, sets the loader tier
    tile: tuple[int, int]  # the belt tile at the edge: first tile of an input belt, last tile of an output belt
    direction: int  # flow direction of that belt (N=0 E=4 S=8 W=12)
    rate: float  # input: informational (fed at full belt rate); output: the target items/s
    # items per belt slot, 1-4 (above 1 needs belt stacking researched). The harness feeds an input above 1 by
    # script, since loaders can't stack; an output drains through its loader at any stack.
    stack: int = 1


Generator = Callable[[dict], tuple[list, list[str], list[Port]]]
Check = Callable[[object], list[str]]  # blueprint -> problems
# request -> candidate specs for the optimiser. A request is {"item": name, "rate": items/s} plus any overrides the
# generator accepts (e.g. "quality"). Yield nothing for an item the generator doesn't make. Yield only specs the solver
# says could pass the harness (bottleneck at or above its 98% output bar, without a safety margin), since the
# optimiser may run every one of them.
Variants = Callable[[dict], Iterable[dict]]
REGISTRY: dict[str, Generator] = {}
# Layout-specific checks (e.g. "inserters move ore -> furnace"); keyed by type so they survive wrapping a generator.
CHECKS: dict[str, tuple[Check, ...]] = {}
VARIANTS: dict[str, Variants] = {}
# technology state the harness needs for this type ("none" or "all"): M2 blocks need belt stacking and hand size
RESEARCH: dict[str, str] = {}


def register(name: str, checks: tuple[Check, ...] = (), variants: Variants | None = None, research: str = "none"):
    if research not in ("none", "all"):
        raise ValueError(f"research must be 'none' or 'all', got {research!r}")

    def deco(fn: Generator) -> Generator:
        REGISTRY[name] = fn
        CHECKS[name] = checks
        RESEARCH[name] = research
        if variants is not None:
            VARIANTS[name] = variants
        return fn

    return deco


def get(name: str) -> Generator:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SpecError(f"unknown blueprint type {name!r}; available: {sorted(REGISTRY)}") from None


from . import circuit_block, plant_array, smelting_column, steel_column  # noqa: E402,F401  (register themselves)
