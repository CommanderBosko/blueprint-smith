"""Run one blueprint in a headless Factorio (create, then benchmark) and parse what the harness mod measured.

Each run gets a fresh temp dir with its own config.ini (two servers can't share a write-data dir), a mods/ dir
enabling the harness mod, and a generated job.lua the mod `require`s. See docs/m1-harness-plan.md, "Contract".
"""
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .server import find_server

MOD_DIR = Path(__file__).parent / "mod"
MOD_NAME = "bps-harness"
ENABLED_MODS = ("base", "elevated-rails", "quality", "space-age", MOD_NAME)
RESULT_FILE = "bps-result.json"  # the mod writes it to <write-data>/script-output/
RESULT_VERSION = 1
PORT_FIELDS = ("role", "item", "belt", "tile", "direction", "rate", "stack")
PORT_DEFAULTS = {"stack": 1}  # optional port fields, for ports written before they existed
MAX_STACK = 4  # items per belt slot (the utility constant max_belt_stack_size)
TAIL_CHARS = 4000


class HarnessError(Exception):
    """The server failed to run a job, or left no readable result."""


@dataclass(frozen=True)
class BuildStatus:
    ghosts_left: int
    proxies_left: int  # item-request proxies (modules) the mod couldn't fulfil
    errors: list[str]


@dataclass(frozen=True)
class OutputMeasure:
    item: str
    target: float  # items/s the output port promises
    count: int  # items sunk during the window
    rate: float  # items/s over the window
    lane_rates: list[float]  # items/s per belt lane (left, right)
    measured: bool = True  # False: an output port the result has no entry for
    # items/s the machines crafted (finished crafts plus progress). Unlike `rate`, it doesn't alias with
    # furnaces that finish in step. None: not reported.
    produced_rate: float | None = None


@dataclass(frozen=True)
class MachineMeasure:
    name: str
    position: tuple[float, float]  # entity centre, game coordinates
    working: float  # share of window ticks spent working/normal
    statuses: dict[str, int]  # entity_status name -> ticks
    recipe: str | None = None  # recipe at the end of the window
    crafts: float = 0.0  # crafts during the window, counting partial progress
    output_growth: int = 0  # items added to the machine's result slots over the window: > 0 means backing up
    quality: str | None = None  # entity quality; None: not reported
    crafting_speed: float | None = None  # at the end of the window, with modules, beacons and quality
    productivity: float | None = None  # productivity bonus at the end of the window (modules and research)
    # inserters unloading it, by where they drop: "machine", "belt", "other", "nothing"; empty: not reported
    unloads: dict[str, int] = field(default_factory=dict)
    unload_hand: int | None = None  # the biggest hand among the inserters unloading it; None: not reported


@dataclass(frozen=True)
class InserterMeasure:
    name: str
    position: tuple[float, float]  # entity centre, relative to the blueprint's top-left like a machine's
    moved: int  # items it let go of during the window (onto a belt, into an entity or the ground)
    rate: float  # items/s over the window
    statuses: dict[str, int]  # entity_status name -> ticks
    quality: str | None = None
    hand: int | None = None  # inserter_target_pickup_count at the end of the window: hand size with research


@dataclass(frozen=True)
class PowerMeasure:
    harness_linked: bool | None  # the harness power source shares a network with the blueprint; None: not reported
    unpowered_machine_ticks: int
    other_networks: int  # electric networks among the blueprint's poles besides the harness one


@dataclass(frozen=True)
class HarnessResult:
    build: BuildStatus
    ticks: dict[str, int]  # {"warmup": W, "window": N}
    outputs: list[OutputMeasure]
    machines: list[MachineMeasure]
    power: PowerMeasure
    series: list[float]  # output items/s per bucket across the run, for spotting ramp-up and bursts
    wall: dict[str, float]  # seconds per server step: {"create": s, "benchmark": s}
    raw: dict  # the result JSON as written
    run_dir: Path | None = None  # set when the run dir was kept (keep_dir=True)
    inserters: list[InserterMeasure] = field(default_factory=list)


# --- job files ---------------------------------------------------------------------------------------------

def config_ini(write_dir: Path) -> str:
    return f"[path]\nread-data=__PATH__executable__/../../data\nwrite-data={write_dir}\n"


def mod_list() -> dict:
    return {"mods": [{"name": n, "enabled": True} for n in ENABLED_MODS]}


def mod_version(mod_dir: Path) -> str:
    try:
        return json.loads((mod_dir / "info.json").read_text())["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return "0.1.0"


def lua_string(s: str) -> str:
    """A Lua 5.2 literal for `s`. Long brackets, at the lowest level whose closer first appears at the very end
    (so content ending in "]" or "]=" can't close early). Not JSON: Lua 5.2 has no \\uXXXX escapes."""
    if "\r" in s:  # long brackets turn CR and CRLF into LF, so spell every byte out instead
        return '"' + "".join(chr(b) if 32 <= b < 127 and b not in b'"\\' else f"\\{b:03d}" for b in s.encode()) + '"'
    level = 0
    while (s + f"]{'=' * level}]").find(f"]{'=' * level}]") != len(s):
        level += 1
    eq = "=" * level
    lead = "\n" if s.startswith("\n") else ""  # Lua drops a newline right after the opening bracket
    return f"[{eq}[{lead}{s}]{eq}]"


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_KEYWORDS = frozenset("and break do else elseif end false for function goto if in local nil not or repeat return "
                      "then true until while".split())


def _lua_key(k: str) -> str:
    return k if _IDENT.match(k) and k not in _KEYWORDS else f"[ {lua_string(k)} ]"


def lua_value(v) -> str:
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            raise ValueError(f"can't write {v!r} to job.lua")
        return repr(v)
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua_value(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_lua_key(str(k))} = {lua_value(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"can't write {type(v).__name__} to job.lua")


def _port_get(port, name: str):
    if name in PORT_DEFAULTS:
        d = PORT_DEFAULTS[name]
        return port.get(name, d) if isinstance(port, dict) else getattr(port, name, d)
    return port[name] if isinstance(port, dict) else getattr(port, name)


def port_table(port) -> dict:
    """A Port (or any object/dict with its fields) as the plain table job.lua carries. Raises ValueError on a
    stack outside 1..MAX_STACK."""
    t = {f: _port_get(port, f) for f in PORT_FIELDS}
    x, y = t["tile"]
    t["tile"] = [x, y]
    s = t["stack"]
    if isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= MAX_STACK:
        raise ValueError(f"{t['role']} port {t['item']} at {tuple(t['tile'])}: stack must be an integer from 1 to "
                         f"{MAX_STACK}, got {s!r}")
    return t


@dataclass(frozen=True)
class Probe:
    """Script help for one machine of a measurement blueprint, so the link under test is its only bottleneck.
    `tile` is any tile the machine covers, relative to the blueprint's top-left like a port's. Every tick the mod
    tops up each `feed` item in its input to a full stack, and `drain` empties its output."""

    tile: tuple[int, int]
    feed: tuple[str, ...] = ()
    drain: bool = False


def probe_table(probe: Probe) -> dict:
    x, y = probe.tile
    if isinstance(probe.feed, str) or not all(isinstance(i, str) for i in probe.feed):
        raise ValueError(f"probe at {tuple(probe.tile)}: feed must be a sequence of item names, got {probe.feed!r}")
    return {"tile": [x, y], "feed": list(probe.feed), "drain": bool(probe.drain)}


RESEARCH = ("none", "all")  # "none": base stats, as ratios.py assumes; "all": every technology (productivity too)


def job_lua(blueprint: str, ports, *, warmup_ticks: int, window_ticks: int, research: str = "none",
            probes=()) -> str:
    if research not in RESEARCH:
        raise ValueError(f"research must be one of {RESEARCH}, got {research!r}")
    fields = {"blueprint": blueprint, "ports": [port_table(p) for p in ports],
              "warmup_ticks": warmup_ticks, "window_ticks": window_ticks, "research": research,
              "probes": [probe_table(p) for p in probes]}
    return "return {\n" + "".join(f"  {k} = {lua_value(v)},\n" for k, v in fields.items()) + "}\n"


def prepare(run_dir: Path, job: str, mod_dir: Path | None = None) -> None:
    """Lay out config.ini, write/, mods/mod-list.json and the harness mod (with `job` as its job.lua)."""
    mod_dir = MOD_DIR if mod_dir is None else mod_dir
    if not (mod_dir / "control.lua").is_file():
        raise HarnessError(f"harness mod not found: {mod_dir / 'control.lua'} is missing")
    (run_dir / "write").mkdir()
    (run_dir / "config.ini").write_text(config_ini(run_dir / "write"))
    mods = run_dir / "mods"
    mods.mkdir()
    (mods / "mod-list.json").write_text(json.dumps(mod_list(), indent=2) + "\n")
    dest = mods / f"{MOD_NAME}_{mod_version(mod_dir)}"
    shutil.copytree(mod_dir, dest, ignore=shutil.ignore_patterns("job.lua", "__pycache__"))
    (dest / "job.lua").write_text(job)


# --- running -------------------------------------------------------------------------------------------------

def _text(b) -> str:
    if b is None:
        return ""
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else b


def _tail(output: str, run_dir: Path) -> str:
    output = output.strip()
    if not output:  # fall back on the server's own log
        try:
            output = (run_dir / "write" / "factorio-current.log").read_text(errors="replace").strip()
        except OSError:
            return "(no server output)"
    return output[-TAIL_CHARS:]


def _step(name: str, cmd: list[str], run_dir: Path, deadline: float) -> tuple[float, str]:
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=run_dir, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=max(1.0, deadline - t0))
    except subprocess.TimeoutExpired as e:
        out = _text(e.stdout) + _text(e.stderr)
        raise HarnessError(f"{name} timed out after {time.monotonic() - t0:.0f}s\n{_tail(out, run_dir)}") from None
    except OSError as e:
        raise HarnessError(f"can't start the server for {name}: {e}") from None
    out = _text(p.stdout) + _text(p.stderr)
    if p.returncode:
        raise HarnessError(f"{name} exited with {p.returncode}\n{_tail(out, run_dir)}")
    return time.monotonic() - t0, out


def run(blueprint: str, ports, *, warmup_ticks: int, window_ticks: int = 3600, research: str = "none",
        probes=(), server: Path | None = None, tmp_root: Path | None = None, keep_dir: bool = False,
        timeout: float = 300) -> HarnessResult:
    """Paste `blueprint` on a lab surface, feed its input ports and sink its output ports, run warmup then a
    measured window, and return the measurements. `probes` script-feed or drain chosen machines (measurements
    only). `timeout` covers both server steps. Raises HarnessUnavailable without a 2.0.77 server and HarnessError
    when a run fails (its dir is then kept and named in the message)."""
    if warmup_ticks < 0 or window_ticks <= 0:
        raise ValueError(f"need warmup_ticks >= 0 and window_ticks > 0, got {warmup_ticks} and {window_ticks}")
    binary = find_server(server)
    job = job_lua(blueprint, ports, warmup_ticks=warmup_ticks, window_ticks=window_ticks,
                  research=research, probes=probes)  # bad ports and probes fail here
    if tmp_root is not None:
        Path(tmp_root).mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="bps-harness-", dir=tmp_root))
    try:
        prepare(run_dir, job)
        base = [str(binary), "-c", str(run_dir / "config.ini"), "--mod-directory", str(run_dir / "mods")]
        save = str(run_dir / "save.zip")
        deadline = time.monotonic() + timeout
        wall = {}
        wall["create"], _ = _step("create", base + ["--create", save], run_dir, deadline)
        wall["benchmark"], out = _step(
            "benchmark", base + ["--benchmark", save, "--benchmark-ticks", str(warmup_ticks + window_ticks + 2)],
            run_dir, deadline)
        result_file = run_dir / "write" / "script-output" / RESULT_FILE
        if not result_file.is_file():
            raise HarnessError(f"the benchmark finished but wrote no script-output/{RESULT_FILE}\n"
                               f"{_tail(out, run_dir)}")
        try:
            data = json.loads(result_file.read_text())
        except ValueError as e:
            raise HarnessError(f"{RESULT_FILE} isn't JSON: {e}") from None
        result = parse_result(data, ports, warmup_ticks=warmup_ticks, window_ticks=window_ticks, wall=wall,
                              run_dir=run_dir if keep_dir else None)
    except HarnessError as e:
        raise HarnessError(f"harness run failed (run dir kept: {run_dir}): {e}") from None
    except OSError as e:
        raise HarnessError(f"harness run failed (run dir kept: {run_dir}): {e}") from e
    if not keep_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    return result


# --- parsing -------------------------------------------------------------------------------------------------

def _list(v) -> list:
    """helpers.table_to_json writes an empty Lua table as {} (and a holey array as a dict of "1", "2"...)."""
    if v is None:
        return []
    if isinstance(v, dict):
        if not v:
            return []
        return [v[k] for k in sorted(v, key=int)]  # ValueError on a real object: malformed
    if isinstance(v, list):
        return v
    raise TypeError(f"expected a list, got {v!r}")


def _dict(v) -> dict:
    if v is None or v == []:
        return {}
    if isinstance(v, dict):
        return v
    raise TypeError(f"expected an object, got {v!r}")


def _float(v) -> float | None:
    return None if v is None else float(v)


def _position(p) -> tuple[float, float]:
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    x, y = _list(p)[:2]
    return float(x), float(y)


def parse_result(data: dict, ports=(), *, warmup_ticks: int | None = None, window_ticks: int | None = None,
                 wall: dict | None = None, run_dir: Path | None = None) -> HarnessResult:
    """The mod's result JSON -> HarnessResult. Output targets come from the output ports (matched by item,
    else in order); an output port the result never mentions becomes an unmeasured OutputMeasure. Ticks given
    here must match the result's. Raises HarnessError on anything malformed."""
    try:
        return _parse(data, ports, warmup_ticks, window_ticks, wall or {}, run_dir)
    except HarnessError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
        raise HarnessError(f"malformed {RESULT_FILE}: {type(e).__name__}: {e}") from None


def _parse(data, ports, warmup_ticks, window_ticks, wall, run_dir) -> HarnessResult:
    data = _dict(data)
    version = data.get("version", RESULT_VERSION)
    if version != RESULT_VERSION:
        raise HarnessError(f"{RESULT_FILE} is version {version}, this runner reads version {RESULT_VERSION}")
    for key in ("build", "outputs", "machines"):
        if key not in data:
            raise HarnessError(f"malformed {RESULT_FILE}: no {key!r}")

    t = _dict(data.get("ticks"))
    ticks = {"warmup": int(t.get("warmup", warmup_ticks if warmup_ticks is not None else -1)),
             "window": int(t.get("window", window_ticks if window_ticks is not None else -1))}
    asked = {"warmup": warmup_ticks, "window": window_ticks}
    for k, want in asked.items():
        if want is not None and ticks[k] != want:
            raise HarnessError(f"{RESULT_FILE} measured {k} {ticks[k]} ticks but the job asked for {want}")

    b = _dict(data["build"])
    build = BuildStatus(int(b.get("ghosts_left", 0)), int(b.get("proxies_left", 0)),
                        [str(e) for e in _list(b.get("errors"))])

    out_ports = [p for p in ports if _port_get(p, "role") == "output"]
    outputs = []
    for o in _list(data["outputs"]):
        o = _dict(o)
        item = o.get("item")
        port = next((p for p in out_ports if _port_get(p, "item") == item), None) if item else None
        if port is None and not item and out_ports:
            port = out_ports[0]  # the mod didn't name it: take the ports in order
        if port is not None:
            out_ports.remove(port)
        count = int(o.get("count", 0))
        if "rate" in o:
            rate = float(o["rate"])
        elif ticks["window"] > 0:
            rate = count * 60 / ticks["window"]
        else:
            raise HarnessError(f"malformed {RESULT_FILE}: an output has no rate and the window is unknown")
        target = o.get("target", _port_get(port, "rate") if port is not None else 0.0)
        outputs.append(OutputMeasure(
            item=str(item or (_port_get(port, "item") if port is not None else "?")),
            target=float(target), count=count, rate=rate,
            lane_rates=[float(x) for x in _list(o.get("lane_rates"))],
            produced_rate=_float(o.get("produced_rate"))))
    outputs += [OutputMeasure(str(_port_get(p, "item")), float(_port_get(p, "rate")), 0, 0.0, [], measured=False)
                for p in out_ports]

    machines = []
    for m in _list(data["machines"]):
        m = _dict(m)
        machines.append(MachineMeasure(
            name=str(m["name"]), position=_position(m["position"]), working=float(m["working"]),
            statuses={str(k): int(v) for k, v in _dict(m.get("statuses")).items()},
            recipe=m.get("recipe"), crafts=float(m.get("crafts", 0.0)), output_growth=int(m.get("output_growth", 0)),
            quality=m.get("quality"), crafting_speed=_float(m.get("crafting_speed")),
            productivity=_float(m.get("productivity")),
            unloads={str(k): int(v) for k, v in _dict(m.get("unloads")).items()},
            unload_hand=None if m.get("unload_hand") is None else int(m["unload_hand"])))

    inserters = []
    for i in _list(data.get("inserters")):
        i = _dict(i)
        moved = int(i.get("moved", 0))
        inserters.append(InserterMeasure(
            name=str(i["name"]), position=_position(i["position"]), moved=moved,
            rate=moved * 60 / ticks["window"] if ticks["window"] > 0 else 0.0,
            statuses={str(k): int(v) for k, v in _dict(i.get("statuses")).items()},
            quality=i.get("quality"), hand=None if i.get("hand") is None else int(i["hand"])))

    p = _dict(data.get("power"))
    linked = p.get("harness_linked")
    others = p.get("other_networks", 0)
    power = PowerMeasure(
        harness_linked=None if linked is None else bool(linked),
        unpowered_machine_ticks=int(p.get("unpowered_machine_ticks", 0)),
        other_networks=len(others) if isinstance(others, (list, dict)) else int(others))

    series = [float(x) for x in _list(data.get("series", data.get("series_per_s")))]
    return HarnessResult(build=build, ticks=ticks, outputs=outputs, machines=machines, power=power, series=series,
                         wall=dict(wall), raw=data, run_dir=run_dir, inserters=inserters)
