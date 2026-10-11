"""HarnessResult -> pass/fail: the build completed, every output meets its target, every machine kept busy,
and the harness power reached the blueprint. Thresholds are inclusive."""
from dataclasses import dataclass

from .runner import HarnessResult, MachineMeasure, OutputMeasure

WORKING = ("working", "normal")
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


def _blocker(m: MachineMeasure) -> str | None:
    """The machine's most frequent non-working status."""
    idle = sorted((-n, s) for s, n in m.statuses.items() if s not in WORKING and n > 0)
    return idle[0][1] if idle else None


def _where(m: MachineMeasure) -> str:
    x, y = m.position
    return f"{m.name} at ({x:g}, {y:g})"


def judged_rate(o: OutputMeasure) -> float:
    """The rate the output bar applies to: crafted when the harness reports it, else what reached the sink."""
    return o.rate if o.produced_rate is None else o.produced_rate


def judge(result: HarnessResult, *, rate_min: float = 0.98, working_min: float = 0.95) -> Verdict:
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

    for m in result.machines:
        if m.output_growth > GROWTH_MAX:
            problems.append(f"{_where(m)}: output backing up, {m.output_growth} more items waiting in it than when "
                            f"the window opened")
        if m.working < working_min - EPS:
            why = _blocker(m)
            problems.append(f"{_where(m)}: working {m.working:.1%} of the window (needs >= {_pct(working_min)})"
                            + (f", mostly {why}" if why else ""))

    if result.power.harness_linked is False:
        problems.append("power: the harness power source isn't on the blueprint's electric network")

    return Verdict(passed=not problems, problems=problems, summary=_summary(result))


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
        low = min(r.machines, key=lambda m: m.working)
        lines.append(f"machines: {len(r.machines)}, min working {low.working:.1%} ({_where(low)})")
    else:
        lines.append("machines: none measured")
    p = r.power
    linked = {True: "linked", False: "NOT linked", None: "link not reported"}[p.harness_linked]
    line = f"power: harness {linked}, {p.unpowered_machine_ticks} unpowered machine-ticks"
    if p.other_networks:
        line += f", {p.other_networks} other network(s)"
    lines.append(line)
    if r.wall:
        steps = ", ".join(f"{k} {v:.1f}s" for k, v in r.wall.items())
        lines.append(f"wall: {steps} for {r.ticks.get('warmup')} warmup + {r.ticks.get('window')} window ticks")
    return lines
