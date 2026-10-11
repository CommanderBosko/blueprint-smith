"""Generator registry. A generator takes a spec dict and returns (entities, notes, ports)."""
from collections.abc import Callable
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


Generator = Callable[[dict], tuple[list, list[str], list[Port]]]
Check = Callable[[object], list[str]]  # blueprint -> problems
REGISTRY: dict[str, Generator] = {}
# Layout-specific checks (e.g. "inserters move ore -> furnace"); keyed by type so they survive wrapping a generator.
CHECKS: dict[str, tuple[Check, ...]] = {}


def register(name: str, checks: tuple[Check, ...] = ()):
    def deco(fn: Generator) -> Generator:
        REGISTRY[name] = fn
        CHECKS[name] = checks
        return fn

    return deco


def get(name: str) -> Generator:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SpecError(f"unknown blueprint type {name!r}; available: {sorted(REGISTRY)}") from None


from . import smelting_column, steel_column  # noqa: E402,F401  (register themselves)
