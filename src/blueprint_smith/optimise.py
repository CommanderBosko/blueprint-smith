"""Find the smallest blueprint for a request that passes the headless harness (M2 piece F).

A request is {"item": name, "rate": items/s} plus any overrides the generators accept (e.g. "quality"). Every
generator with variants proposes candidate specs (generators.VARIANTS); each is built and ranked by footprint
(bounding-box tiles, input and output belts included), then estimated power, then its JSON, so ties are stable.
The harness runs them best-first in parallel batches. Batches go in rank order, so once a batch holds a pass,
nothing ranked above the best pass is left unrun, and the search stops there (PROJECT_BRIEF v2).
"""
import json
import math
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from draftsman.data import recipes

from . import checks, effects, generators
from .errors import BuildError, SpecError
from .evaluate import evaluate
from .pipeline import BuildResult, build

TICKS = 60
MAX_JOBS = 8  # harness runs at once by default (capped by the CPU count); each run takes about 6 s
_PREFIX = {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


@dataclass
class Candidate:
    spec: dict
    built: BuildResult
    width: int
    height: int
    tiles: int
    power: float  # watts, estimated by `power_estimate`; a tie-break only
    evaluation: object | None = None  # evaluate.Evaluation once the harness has run it

    @property
    def rank(self) -> tuple:
        return self.tiles, self.power, _key(self.spec)


@dataclass
class Optimised:
    winner: Candidate | None  # the best-ranked candidate that passed the harness
    candidates: list[Candidate]  # every spec that built, best-ranked first; evaluation is None for those never run
    rejected: list[tuple[object, str]]  # (spec, why it didn't build)
    runs: int  # harness runs

    @property
    def variants(self) -> int:
        return len(self.candidates) + len(self.rejected)


def _key(spec) -> str:
    return json.dumps(spec, sort_keys=True, default=str)


def footprint(bp) -> tuple[int, int]:
    """(width, height) in whole tiles of the blueprint's bounding box: every entity, the input and output belts
    included (PROJECT_BRIEF v2). Collision boxes sit just inside their tiles, so the edges round outward."""
    box = bp.get_world_bounding_box()
    if box is None:
        return 0, 0
    (x1, y1), (x2, y2) = box.top_left, box.bot_right
    return math.ceil(x2 - 1e-6) - math.floor(x1 + 1e-6), math.ceil(y2 - 1e-6) - math.floor(y1 + 1e-6)


def _energy(text, unit: str) -> float:
    """'40kJ' -> 40000.0 with unit 'J'; '1kW' -> 1000.0 with unit 'W'."""
    m = re.fullmatch(rf"\s*([0-9.eE+-]+)\s*([kMGT]?){unit}\s*", str(text))
    if not m:
        raise SpecError(f"can't read energy {text!r}")
    return float(m[1]) * _PREFIX[m[2]]


def inserter_power(inserter) -> float:
    """An upper bound on the watts one inserter draws: its drain plus both hand motions running flat out every
    tick, 60 x (energy_per_rotation x rotation_speed + energy_per_movement x extension_speed). That's the game's
    "max consumption" (1.1's stack inserter: 20 kJ x (0.04 + 0.07) x 60 = 132 kW); 2.0's stack inserter gives
    337 kW. Quality is assumed to speed both motions like crafting speed (x2.5 legendary) at the same energy per
    motion, which still bounds it if quality speeds only one. A real inserter rests between swings, so it draws
    less. heating_energy is for frozen planets only, and a burner inserter burns fuel, not power (0 here)."""
    proto = inserter.prototype
    source = proto.get("energy_source") or {}
    if source.get("type") != "electric":
        return 0.0
    per_tick = (_energy(proto.get("energy_per_rotation", "0J"), "J") * proto.get("rotation_speed", 0)
                + _energy(proto.get("energy_per_movement", "0J"), "J") * proto.get("extension_speed", 0))
    speed = effects.quality_multiplier(getattr(inserter, "quality", None) or "normal")
    drain = _energy(source["drain"], "W") if "drain" in source else 0.0
    return drain + TICKS * per_tick * speed


def _machine_power(machine, beacons, research) -> float:
    if getattr(machine, "recipe", None):
        return effects.entity_rates(machine, beacons=beacons, research=research).power
    # A furnace carries no recipe in a blueprint. Its power doesn't depend on the recipe, so any it crafts will do.
    categories = machine.prototype.get("crafting_categories", [])
    quality = getattr(machine, "quality", None) or "normal"
    for name, recipe in recipes.raw.items():
        if recipe.get("category", "crafting") in categories:
            try:
                return effects.machine_rates(machine.name, name, quality=quality, modules=effects.modules_of(machine),
                                             beacons=beacons, research=research).power
            except SpecError:
                continue
    return 0.0


def power_estimate(bp, research: str = "none") -> float:
    """Watts the blueprint draws at full tilt, for breaking footprint ties (power is the brief's tiebreak) and
    nothing else: crafting machines working (effects.entity_rates: quality, modules, the beacons reaching them),
    beacons (effects.beacon_power) and an upper bound per inserter (`inserter_power`). Belts and poles draw none;
    other consumers (drills, labs) aren't counted."""
    targets = checks.beacon_targets(bp)
    watts = 0.0
    for e in bp.entities:
        kind = e.prototype.get("type")
        if "crafting_speed" in e.prototype:
            watts += _machine_power(e, targets.get(e, []), research)
        elif kind == "beacon":
            watts += effects.beacon_power(e)
        elif kind == "inserter":
            watts += inserter_power(e)
    return watts


def _check_request(request) -> None:
    if not isinstance(request, dict):
        raise SpecError(f"a request must be an object like {{\"item\": \"electronic-circuit\", \"rate\": 240}}, "
                        f"got {request!r}")
    item, rate = request.get("item"), request.get("rate")
    if not isinstance(item, str) or not item:
        raise SpecError(f"'item' must be an item name, got {item!r}")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise SpecError(f"'rate' must be a number of {item}/s above 0, got {rate!r}")


def _variants(request: dict) -> list:
    """Every generator's candidate specs, in type order, duplicates dropped."""
    specs, seen = [], set()
    for name in sorted(generators.VARIANTS):
        for spec in generators.VARIANTS[name](dict(request)):
            if (k := _key(spec)) not in seen:
                seen.add(k)
                specs.append(spec)
    if not specs:
        raise SpecError(f"no generator makes {request['rate']:g} {request['item']}/s; the types with variants are "
                        f"{', '.join(sorted(generators.VARIANTS)) or 'none'}")
    return specs


def optimise(request: dict, *, evaluator: Callable | None = None, jobs: int | None = None,
             max_runs: int | None = None, keep_dir: bool = False) -> Optimised:
    """The smallest-footprint candidate for `request` that passes the harness (ties: less power), or no winner.

    Builds serially, since pipeline.build records warnings process-wide; a spec that fails to build is rejected,
    not fatal. `WARNING:` notes don't filter: variants are solver-feasible by contract, and the harness decides the
    borderline ones. Then up to `jobs` harness runs at once (default min(8, CPUs)), at most `max_runs` in all.
    `evaluator(built, research=..., keep_dir=...)` defaults to evaluate.evaluate; research is the type's declared
    generators.RESEARCH. Raises SpecError for a bad request or one no generator makes; harness.HarnessUnavailable
    and harness.HarnessError propagate."""
    _check_request(request)
    if jobs is not None and jobs < 1:
        raise ValueError(f"jobs must be at least 1, got {jobs}")
    if max_runs is not None and max_runs < 0:
        raise ValueError(f"max_runs can't be negative, got {max_runs}")
    evaluator = evaluator or evaluate
    jobs = jobs or min(MAX_JOBS, os.cpu_count() or 1)

    candidates, rejected = [], []
    for spec in _variants(request):
        try:
            built = build(spec)
        except SpecError as e:
            rejected.append((spec, str(e)))
            continue
        except BuildError as e:
            rejected.append((spec, "; ".join(e.problems)))
            continue
        width, height = footprint(built.blueprint)
        power = power_estimate(built.blueprint, generators.RESEARCH.get(spec["type"], "none"))
        candidates.append(Candidate(spec, built, width, height, width * height, power))
    candidates.sort(key=lambda c: c.rank)

    runs, winner = 0, None
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while winner is None and runs < len(candidates):
            size = jobs if max_runs is None else min(jobs, max_runs - runs)
            if size <= 0:
                break
            batch = candidates[runs:runs + size]
            futures = [pool.submit(evaluator, c.built, research=generators.RESEARCH.get(c.spec["type"], "none"),
                                   keep_dir=keep_dir) for c in batch]
            for c, f in zip(batch, futures):
                c.evaluation = f.result()
            runs += len(batch)
            # every candidate ranked above this batch has run and failed, so its best pass is the winner
            winner = next((c for c in batch if c.evaluation.verdict.passed), None)
    return Optimised(winner, candidates, rejected, runs)
