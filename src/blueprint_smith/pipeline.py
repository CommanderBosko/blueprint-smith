"""spec dict -> validated blueprint string. Draftsman only warns on bad layouts; here every warning is a failure."""
import warnings
from dataclasses import dataclass, field

from draftsman.blueprintable import Blueprint

from . import checks, generators
from .errors import BuildError, SpecError


@dataclass
class BuildResult:
    string: str
    blueprint: Blueprint
    notes: list[str] = field(default_factory=list)


def build(spec: dict) -> BuildResult:
    if not isinstance(spec, dict) or "type" not in spec:
        raise SpecError("spec must be an object with a 'type' field")
    generator = generators.get(spec["type"])

    problems: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        entities, notes = generator(spec)
        bp = Blueprint()
        bp.label = spec.get("label", spec["type"])
        for e in entities:
            bp.entities.append(e)
        # Pasted blueprints keep only the wires they carry: the game won't join poles inside one.
        # Axis-only keeps the wiring a tidy grid; pole_network flags any pole this leaves unjoined.
        bp.generate_power_connections(only_axis=True)
        string = bp.to_string()
    problems += [f"{type(w.message).__name__}: {w.message}" for w in caught]
    for check in (*checks.ALL_CHECKS, *generators.CHECKS.get(spec["type"], ())):
        problems += check(bp)
    if problems:
        raise BuildError(problems)
    return BuildResult(string=string, blueprint=bp, notes=notes)
