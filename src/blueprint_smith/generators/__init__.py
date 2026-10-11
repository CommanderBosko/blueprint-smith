"""Generator registry. A generator takes a spec dict and returns (entities, notes)."""
from collections.abc import Callable

from ..errors import SpecError

Generator = Callable[[dict], tuple[list, list[str]]]
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
