"""HarnessResult -> pass/fail: the build completed, every output meets its target, no machine was blocked on
output, and the harness power reached the blueprint. Thresholds are inclusive.

Idle time ("no ingredients") doesn't fail a machine: beacons come in whole steps, so an honest design runs some
machines under capacity. The output bar catches a starved line, and each machine's share working is reported as
utilisation instead of judged (docs/m2-plan.md, "Decided: the machine bar"). For the same reason a machine that
unloads only into other machines isn't judged on blocking or on output growth: under direct insertion its consumer
sets the pace, so spare capacity shows as blocked rather than idle, and its buffer fills to a cap and waits rather
than jamming anything (user, 2026-10-12). Unpowered time isn't judged either: power is never short in the
user's save, so it's only reported."""
from dataclasses import dataclass

from .runner import HarnessResult, MachineMeasure, OutputMeasure

WORKING = ("working", "normal")
# Stopped because its results have nowhere to go (2.0.77 defines.entity_status): result slots full; a machine that
# places its results itself (vector_to_place_result) waiting for room; a burner's burnt-result slot full.
BLOCKED = ("full_output", "waiting_for_space_in_destination", "full_burnt_result_output")
EPS = 1e-9  # absorbs float noise such as 0.98 * 15, so exactly-at-threshold passes
# The sink count aliases with crafts finishing in step (+-1 craft per machine over the window), so the output
# bar uses the crafted rate; the sink only has to show the items actually arrive.
DELIVERY_MIN = 0.8
# A machine whose result slots gain more than this over the window is backing up, even while it reads "working".
# An inserter takes 1-3 items at a time, so a flowing machine's slots stay within a few items.
GROWTH_MAX = 3


@dataclass(frozen=True)
class Verdict:
    passed: bool
    problems: list[str]  # one line each; empty when passed
    summary: list[str]  # what was measured, pass or fail


def _pct(x: float) -> str:
    return f"{x * 100:g}%"


@dataclass(frozen=True)
class Utilisation:
    """Share of the window working, over the machines of one kind (quality, name and recipe)."""
    name: str
    quality: str | None
    recipe: str | None
    count: int
    working_min: float
    working_mean: float
    lowest: MachineMeasure  # the machine at working_min


def utilisation(machines: list[MachineMeasure]) -> list[Utilisation]:
    """Machines grouped by kind, in order of first appearance."""
    groups: dict[tuple, list[MachineMeasure]] = {}
    for m in machines:
        groups.setdefault((m.name, m.quality, m.recipe), []).append(m)
    return [Utilisation(name, quality, recipe, len(ms), min(m.working for m in ms),
                        sum(m.working for m in ms) / len(ms), min(ms, key=lambda m: m.working))
            for (name, quality, recipe), ms in groups.items()]


def share(m: MachineMeasure, statuses: tuple[str, ...], window: int) -> float:
    """Share of the window `m` spent in any of `statuses` (of the ticks tallied when the window is unknown)."""
    total = window if window > 0 else sum(m.statuses.values())
    return sum(m.statuses.get(s, 0) for s in statuses) / total if total > 0 else 0.0


def feeds_only_machines(m: MachineMeasure) -> bool:
    """Every inserter unloading `m` drops into another machine (user, 2026-10-12: not judged on blocking)."""
    return bool(m.unloads) and set(m.unloads) == {"machine"}


def _most(m: MachineMeasure, statuses: tuple[str, ...]) -> str:
    return max(statuses, key=lambda s: m.statuses.get(s, 0))


def _at(m: MachineMeasure) -> str:
    x, y = m.position
    return f"({x:g}, {y:g})"


def _where(m: MachineMeasure) -> str:
    return f"{m.name} at {_at(m)}"


def judged_rate(o: OutputMeasure) -> float:
    """The rate the output bar applies to: crafted when the harness reports it, else what reached the sink."""
    return o.rate if o.produced_rate is None else o.produced_rate


def judge(result: HarnessResult, *, rate_min: float = 0.98, blocked_max: float = 0.05) -> Verdict:
    problems = []
    b = result.build
    problems += [f"build error: {e}" for e in b.errors]
    if b.ghosts_left > 0:
        problems.append(f"build incomplete: {b.ghosts_left} ghost(s) left unrevived")
    if b.proxies_left > 0:
        problems.append(f"build incomplete: {b.proxies_left} item request(s) left unfulfilled (modules not inserted)")

    if not result.outputs:
        problems.append("no output was measured, so throughput can't be judged")
    for o in result.outputs:
        if not o.measured:
            problems.append(f"output {o.item}: the harness reported nothing for this port")
        elif o.target <= 0:
            problems.append(f"output {o.item}: no positive target rate to judge {judged_rate(o):.2f}/s against "
                            f"(target {o.target:g})")
        elif judged_rate(o) / o.target < rate_min - EPS:
            problems.append(f"output {o.item}: {judged_rate(o):.2f}/s is {judged_rate(o) / o.target:.1%} of the "
                            f"{o.target:g}/s target (needs >= {_pct(rate_min)})")
        if o.measured and o.produced_rate and o.rate < DELIVERY_MIN * o.produced_rate - EPS:
            problems.append(f"output {o.item}: only {o.rate:.2f}/s of the {o.produced_rate:.2f}/s crafted reached "
                            f"the output port")

    window = result.ticks.get("window", 0)
    for m in result.machines:
        if m.output_growth > GROWTH_MAX and not feeds_only_machines(m):
            problems.append(f"{_where(m)}: output backing up, {m.output_growth} more items waiting in it than when "
                            f"the window opened")
        x = share(m, BLOCKED, window)
        if x > blocked_max + EPS and not feeds_only_machines(m):
            problems.append(f"{_where(m)}: blocked on output {x:.1%} of the window (needs <= {_pct(blocked_max)}), "
                            f"mostly {_most(m, BLOCKED)}")

    if result.power.harness_linked is False:
        problems.append("power: the harness power source isn't on the blueprint's electric network")

    return Verdict(passed=not problems, problems=problems, summary=_summary(result))


def _utilisation_line(u: Utilisation) -> str:
    quality = u.quality if u.quality != "normal" else None
    kind = " ".join(x for x in (quality, u.name, f"({u.recipe})" if u.recipe else None) if x)
    if u.count == 1:
        return f"utilisation {kind}: working {u.working_min:.1%} at {_at(u.lowest)}"
    return (f"utilisation {kind} x{u.count}: working min {u.working_min:.1%} at {_at(u.lowest)}, "
            f"mean {u.working_mean:.1%}")


def _summary(r: HarnessResult) -> list[str]:
    lines = []
    for o in r.outputs:
        if not o.measured:
            lines.append(f"{o.item}: not measured")
            continue
        of = f"{judged_rate(o) / o.target:.1%}" if o.target > 0 else "no target"
        lanes = "/".join(f"{x:.2f}" for x in o.lane_rates) or "n/a"
        made = f"crafted {o.produced_rate:.2f}/s, " if o.produced_rate is not None else ""
        lines.append(f"{o.item}: {judged_rate(o):.2f}/s of {o.target:g}/s ({of}); {made}delivered {o.rate:.2f}/s, "
                     f"lanes {lanes}")
    if r.machines:
        window = r.ticks.get("window", 0)
        judged = [m for m in r.machines if not feeds_only_machines(m)]
        worst = max(judged, key=lambda m: share(m, BLOCKED, window), default=None)
        x = share(worst, BLOCKED, window) if worst else 0.0
        line = f"machines: {len(r.machines)}, " + (f"most blocked on output {x:.1%} ({_where(worst)})" if x > 0
                                                    else "none blocked on output")
        fed = [share(m, BLOCKED, window) for m in r.machines if feeds_only_machines(m)]
        if fed:
            line += f"; {len(fed)} feeding only machines, blocked up to {max(fed):.1%}, not judged on it"
        lines.append(line)
        lines += [_utilisation_line(u) for u in utilisation(r.machines)]
    else:
        lines.append("machines: none measured")
    p = r.power
    linked = {True: "linked", False: "NOT linked", None: "not linked (no blueprint pole)"}[p.harness_linked]
    line = f"power: harness {linked}, {p.unpowered_machine_ticks} unpowered machine-ticks"
    if p.other_networks:
        line += f", {p.other_networks} other network(s)"
    lines.append(line)
    if r.wall:
        steps = ", ".join(f"{k} {v:.1f}s" for k, v in r.wall.items())
        lines.append(f"wall: {steps} for {r.ticks.get('warmup')} warmup + {r.ticks.get('window')} window ticks")
    return lines
