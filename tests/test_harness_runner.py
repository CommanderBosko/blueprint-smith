import dataclasses
import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from blueprint_smith import harness
from blueprint_smith.generators import Port
from blueprint_smith.harness import runner, server
from blueprint_smith.harness.runner import (BuildStatus, HarnessError, HarnessResult, InserterMeasure,
                                            MachineMeasure, OutputMeasure, PowerMeasure, Probe, config_ini, job_lua,
                                            lua_string, lua_value, mod_list, parse_result, prepare)
from blueprint_smith.harness.server import HarnessUnavailable, find_server
from blueprint_smith.harness.verdict import judge, utilisation

FIXTURES = Path(__file__).parent / "fixtures" / "harness"
GOOD_VERSION = "Version: 2.0.77 (build 84539, linux64, headless)"


@dataclass(frozen=True)
class FakePort:  # duck-typed stand-in for generators.Port
    role: str
    item: str
    belt: str
    tile: tuple[int, int]
    direction: int
    rate: float


IRON_PORTS = [FakePort("input", "iron-ore", "transport-belt", (0, 0), 8, 15),
              FakePort("output", "iron-plate", "transport-belt", (6, 71), 8, 15)]


def lua_long_string(lit: str) -> tuple[str, str]:
    """Decode a long-bracket literal the way Lua 5.2's llex.c does; returns (value, text after the closer)."""
    assert lit[0] == "["
    i, level = 1, 0
    while lit[i] == "=":
        i, level = i + 1, level + 1
    assert lit[i] == "["
    i += 1
    if lit[i:i + 1] == "\n":
        i += 1
    out = []
    while True:
        if lit[i] == "]":  # skip_sep: consume "]" and any "="; it closes only at the right level followed by "]"
            j = i + 1
            while j < len(lit) and lit[j] == "=":
                j += 1
            if j < len(lit) and lit[j] == "]" and j - i - 1 == level:
                return "".join(out), lit[j + 1:]
            out.append(lit[i:j])
            i = j
        else:
            out.append(lit[i])
            i += 1


def write_script(path: Path, body: str, shebang: str = "/bin/sh") -> Path:
    path.write_text(f"#!{shebang}\n{body}")
    path.chmod(0o755)
    return path


# --- job files ---------------------------------------------------------------------------------------------

def test_config_ini_points_read_data_at_the_install_and_write_data_at_the_run():
    assert config_ini(Path("/tmp/run/write")) == (
        "[path]\nread-data=__PATH__executable__/../../data\nwrite-data=/tmp/run/write\n")


def test_mod_list_enables_space_age_and_the_harness():
    mods = mod_list()["mods"]
    assert [m["name"] for m in mods] == ["base", "elevated-rails", "quality", "space-age", "bps-harness"]
    assert all(m["enabled"] is True for m in mods)


@pytest.mark.parametrize("s, level", [
    ("0eNqlnOtu2zgQhV", 0),
    ("", 0),
    ("a]]b", 1),
    ("]", 1),  # "]" + "]]" would close a char early
    ("a]=", 0),  # "]=" then "]]" still closes at the end
    ("x]=]y", 0),
    ("]=]", 2),
    ("a]=]]b", 2),
    ("]==]", 1),
    ("p]]q]=]r]==]s", 3),
])
def test_lua_string_picks_a_long_bracket_level_the_content_cant_close(s, level):
    lit = lua_string(s)
    eq = "=" * level
    assert lit.startswith(f"[{eq}[") and lit.endswith(f"]{eq}]")
    assert lit[level + 1] == "["  # exactly this level, not higher
    assert lua_long_string(lit) == (s, "")


def test_lua_string_keeps_a_leading_newline_and_avoids_cr():
    assert lua_long_string(lua_string("\nabc")) == ("\nabc", "")
    assert lua_string("a\r\nb\"\\") == '"a\\013\\010b\\034\\092"'  # Lua 5.2 decimal escapes, never \uXXXX
    assert lua_string("é") == "[[é]]"  # UTF-8 passes through a long bracket untouched


def test_lua_value_numbers_tables_and_keys():
    assert lua_value(15) == "15"
    assert lua_value(7.5) == "7.5"
    assert lua_value(0.1) == "0.1"
    assert lua_value(True) == "true" and lua_value(None) == "nil"
    assert lua_value({"a": [1, 2.5], "b": {"c": False}}) == "{a = {1, 2.5}, b = {c = false}}"
    assert lua_value({"end": 1, "my-key": 2}) == "{[ [[end]] ] = 1, [ [[my-key]] ] = 2}"
    with pytest.raises(ValueError):
        lua_value(float("inf"))
    with pytest.raises(TypeError):
        lua_value(object())


def test_job_lua_carries_blueprint_ports_and_ticks():
    bp = "0eNq]]x]=]"  # forces level 2
    ports = [IRON_PORTS[0], {"role": "output", "item": "iron-plate", "belt": "fast-transport-belt",
                             "tile": (6, 71), "direction": 12, "rate": 22.5, "ignored": "x"}]
    job = job_lua(bp, ports, warmup_ticks=7200, window_ticks=3600)
    assert job == (
        "return {\n"
        "  blueprint = [==[0eNq]]x]=]]==],\n"
        "  ports = {"
        "{role = [[input]], item = [[iron-ore]], belt = [[transport-belt]], tile = {0, 0}, direction = 8, rate = 15, "
        "stack = 1}, "
        "{role = [[output]], item = [[iron-plate]], belt = [[fast-transport-belt]], tile = {6, 71}, direction = 12, "
        "rate = 22.5, stack = 1}},\n"
        "  warmup_ticks = 7200,\n"
        "  window_ticks = 3600,\n"
        "  research = [[none]],\n"
        "  probes = {},\n"
        "}\n")


def test_job_lua_carries_probes():
    probe = Probe((3, 4), ("iron-plate", "copper-cable"), drain=True)
    job = job_lua("0e", [], warmup_ticks=1, window_ticks=1, probes=[probe, Probe((0, 0))])
    assert ("  probes = {{tile = {3, 4}, feed = {[[iron-plate]], [[copper-cable]]}, drain = true}, "
            "{tile = {0, 0}, feed = {}, drain = false}},\n") in job


def test_a_probe_feeds_item_names():
    with pytest.raises(ValueError, match="feed must be a sequence of item names"):
        job_lua("0e", [], warmup_ticks=1, window_ticks=1, probes=[Probe((0, 0), "iron-plate")])


def test_inserters_are_parsed_with_their_rate():
    data = {"build": {}, "outputs": [], "machines": [], "ticks": {"warmup": 0, "window": 600},
            "inserters": [{"name": "stack-inserter", "quality": "legendary", "position": {"x": 4.5, "y": 1.5},
                           "moved": 640, "hand": 16, "statuses": {"working": 590, "waiting_for_source_items": 10}}]}
    (i,) = parse_result(data).inserters
    assert i == InserterMeasure("stack-inserter", (4.5, 1.5), 640, 64.0,
                                {"working": 590, "waiting_for_source_items": 10}, "legendary", 16)
    assert parse_result({"build": {}, "outputs": [], "machines": []}).inserters == []


def test_job_lua_carries_the_port_stack():
    stacked = replace(Port(*dataclasses.astuple(IRON_PORTS[0])), stack=4)
    assert "rate = 15, stack = 4}" in job_lua("0e", [stacked], warmup_ticks=1, window_ticks=1)
    assert "stack = 2}" in job_lua("0e", [{**dataclasses.asdict(IRON_PORTS[1]), "stack": 2}], warmup_ticks=1,
                                   window_ticks=1)


@pytest.mark.parametrize("stack", [0, 5, -1, 2.5, True, "4", None])
def test_job_lua_rejects_a_stack_outside_1_to_4(stack):
    with pytest.raises(ValueError, match=f"stack must be an integer from 1 to 4, got {re.escape(repr(stack))}"):
        job_lua("0e", [{**dataclasses.asdict(IRON_PORTS[0]), "stack": stack}], warmup_ticks=1, window_ticks=1)


def test_job_lua_research_is_none_or_all():
    assert "research = [[all]]" in job_lua("0e", [], warmup_ticks=1, window_ticks=1, research="all")
    with pytest.raises(ValueError, match="research must be one of"):
        job_lua("0e", [], warmup_ticks=1, window_ticks=1, research="some")


def fake_mod(tmp_path: Path, version: str | None = "0.3.1") -> Path:
    mod = tmp_path / "fake-mod"
    mod.mkdir()
    (mod / "control.lua").write_text("local job = require('job')\n")
    (mod / "job.lua").write_text("stale")
    if version:
        (mod / "info.json").write_text(json.dumps({"name": "bps-harness", "version": version}))
    return mod


def test_prepare_lays_out_the_run_dir(tmp_path):
    mod = fake_mod(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    prepare(run_dir, "return {}\n", mod_dir=mod)
    assert (run_dir / "write").is_dir()
    assert (run_dir / "config.ini").read_text() == config_ini(run_dir / "write")
    assert json.loads((run_dir / "mods" / "mod-list.json").read_text()) == mod_list()
    installed = run_dir / "mods" / "bps-harness_0.3.1"
    assert (installed / "control.lua").read_text() == "local job = require('job')\n"
    assert (installed / "job.lua").read_text() == "return {}\n"  # the source mod's stale job.lua isn't used


def test_prepare_defaults_the_mod_version_and_needs_control_lua(tmp_path):
    mod = fake_mod(tmp_path, version=None)
    (tmp_path / "a").mkdir()
    prepare(tmp_path / "a", "return {}\n", mod_dir=mod)
    assert (tmp_path / "a" / "mods" / "bps-harness_0.1.0" / "control.lua").is_file()
    (mod / "control.lua").unlink()
    (tmp_path / "b").mkdir()
    with pytest.raises(HarnessError, match="control.lua"):
        prepare(tmp_path / "b", "return {}\n", mod_dir=mod)


# --- parsing -------------------------------------------------------------------------------------------------

def load_fixture(name="iron_15.json") -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_fixture_result():
    r = parse_result(load_fixture(), IRON_PORTS, warmup_ticks=7200, window_ticks=3600, wall={"create": 1.7})
    assert r.build == BuildStatus(0, 0, [])  # errors came as {}
    assert r.ticks == {"warmup": 7200, "window": 3600}
    assert r.outputs == [OutputMeasure("iron-plate", 15.0, 900, 15.0, [7.566666666666666, 7.55])]
    assert len(r.machines) == 3
    assert r.machines[1] == MachineMeasure("electric-furnace", (3.5, 4.5), 0.99,
                                           {"working": 3564, "no_ingredients": 36})
    assert r.power == PowerMeasure(True, 0, 0)
    assert r.series[:2] == [14.9, 15.0]
    assert r.wall == {"create": 1.7}
    assert r.raw["log"] and r.run_dir is None


def test_parse_normalises_empty_tables_written_as_objects():
    data = {"build": {"ghosts_left": 0, "proxies_left": 0, "errors": []},
            "outputs": {}, "machines": {},
            "power": {"unpowered_machine_ticks": 0, "other_networks": {}},
            "series": {}}
    r = parse_result(data, [])
    assert r.outputs == [] and r.machines == [] and r.series == [] and r.build.errors == []
    assert r.power == PowerMeasure(None, 0, 0)  # harness_linked not reported
    # and the other way round: an empty statuses object written as [], lanes as {}, a holey array as a dict
    data = {"build": {"errors": {"1": "a", "2": "b"}}, "ticks": {"warmup": 60, "window": 600},
            "outputs": [{"count": 100, "lane_rates": {}}],
            "machines": [{"name": "assembling-machine-2", "position": {"x": 1.5, "y": 2.5}, "working": 0,
                          "statuses": []}],
            "power": {"harness_linked": False, "other_networks": [7, 9]}}
    r = parse_result(data, IRON_PORTS)
    assert r.build.errors == ["a", "b"]
    assert r.outputs == [OutputMeasure("iron-plate", 15.0, 100, 10.0, [])]  # unnamed: the first output port
    assert r.machines == [MachineMeasure("assembling-machine-2", (1.5, 2.5), 0.0, {})]
    assert r.power == PowerMeasure(False, 0, 2)


def test_parse_marks_output_ports_the_result_never_mentions():
    data = load_fixture()
    data["outputs"] = []
    r = parse_result(data, IRON_PORTS)
    assert r.outputs == [OutputMeasure("iron-plate", 15.0, 0, 0.0, [], measured=False)]
    assert not judge(r).passed


def test_parse_rejects_malformed_and_mismatched_results():
    with pytest.raises(HarnessError, match="'machines'"):
        parse_result({"build": {}, "outputs": []}, [])
    with pytest.raises(HarnessError, match="malformed"):
        parse_result({"build": {}, "outputs": [], "machines": [{"name": "x"}]}, [])
    with pytest.raises(HarnessError, match="version 2"):
        parse_result({**load_fixture(), "version": 2}, [])
    with pytest.raises(HarnessError, match="window 3600 ticks but the job asked for 600"):
        parse_result(load_fixture(), IRON_PORTS, warmup_ticks=7200, window_ticks=600)


# --- verdict -------------------------------------------------------------------------------------------------

def make_result(rate=15.0, target=15.0, working=1.0, statuses=None, **kw) -> HarnessResult:
    base = HarnessResult(
        build=BuildStatus(0, 0, []), ticks={"warmup": 7200, "window": 3600},
        outputs=[OutputMeasure("iron-plate", target, round(rate * 60), rate, [rate / 2, rate / 2])],
        machines=[MachineMeasure("electric-furnace", (3.5, 1.5), working, statuses or {"working": 3600})],
        power=PowerMeasure(True, 0, 0), series=[], wall={"create": 1.7, "benchmark": 3.5}, raw={})
    return replace(base, **kw)


def test_fixture_result_passes():
    v = judge(parse_result(load_fixture(), IRON_PORTS, wall={"create": 1.7, "benchmark": 3.5}))
    assert v.passed and v.problems == []
    assert v.summary == [
        "iron-plate: 15.00/s of 15/s (100.0%); delivered 15.00/s, lanes 7.57/7.55",
        "machines: 3, none blocked on output",
        "utilisation electric-furnace x3: working min 99.0% at (3.5, 4.5), mean 99.7%",
        "power: harness linked, 0 unpowered machine-ticks",
        "wall: create 1.7s, benchmark 3.5s for 7200 warmup + 3600 window ticks",
    ]


@pytest.mark.parametrize("rate, target, passed", [
    (14.7, 15, True),  # exactly 98.0%
    (98.0, 100, True),
    (0.98 * 30, 30, True),
    (15.5, 15, True),
    (14.685, 15, False),  # 97.9%
    (97.9, 100, False),
])
def test_output_rate_threshold_is_inclusive_at_98_percent(rate, target, passed):
    v = judge(make_result(rate=rate, target=target))
    assert v.passed is passed
    if not passed:
        assert v.problems == [f"output iron-plate: {rate:.2f}/s is 97.9% of the {target:g}/s target (needs >= 98%)"]


def machine(statuses: dict[str, int], window: int = 3600, **kw) -> MachineMeasure:
    working = (statuses.get("working", 0) + statuses.get("normal", 0)) / window
    return MachineMeasure("electric-furnace", (3.5, 1.5), working, statuses, **kw)


def with_machines(*machines: MachineMeasure, rate=15.0) -> HarnessResult:
    return make_result(rate=rate, machines=list(machines))


@pytest.mark.parametrize("idle", ["no_ingredients", "item_ingredient_shortage", "fluid_ingredient_shortage",
                                  "no_recipe"])
def test_an_idle_machine_passes(idle):
    """The M2 machine bar: an over-capacity machine waiting for input is reported, not failed."""
    v = judge(with_machines(machine({"working": 2520, idle: 1080})))
    assert v.passed, v.problems
    assert "utilisation electric-furnace: working 70.0% at (3.5, 1.5)" in v.summary


@pytest.mark.parametrize("ticks, passed", [(180, True), (0, True), (181, False), (216, False), (3600, False)])
def test_blocked_on_output_threshold_is_inclusive_at_5_percent(ticks, passed):
    v = judge(with_machines(machine({"working": 3600 - ticks, "full_output": ticks})))
    assert v.passed is passed
    if not passed:
        assert v.problems == [f"electric-furnace at (3.5, 1.5): blocked on output {ticks / 3600:.1%} of the window "
                              f"(needs <= 5%), mostly full_output"]


def test_every_blocked_status_counts_together():
    m = machine({"working": 3384, "full_output": 100, "waiting_for_space_in_destination": 80,
                 "full_burnt_result_output": 36})
    assert judge(with_machines(m)).problems == [
        "electric-furnace at (3.5, 1.5): blocked on output 6.0% of the window (needs <= 5%), mostly full_output"]
    assert judge(with_machines(machine({"working": 3384, "waiting_for_space_in_destination": 216}))).problems == [
        "electric-furnace at (3.5, 1.5): blocked on output 6.0% of the window (needs <= 5%), mostly "
        "waiting_for_space_in_destination"]


@pytest.mark.parametrize("statuses", [
    {"working": 3240, "no_power": 360},
    {"working": 3400, "no_power": 100, "low_power": 100},
    {"no_power": 3600},
    {"low_power": 3600},
])
def test_unpowered_time_is_not_judged(statuses):
    """Power is never short in the user's save (user, 2026-10-12): only the output bar sees an unpowered line."""
    v = judge(with_machines(machine(statuses)))
    assert v.passed, v.problems


@pytest.mark.parametrize("unloads, passed", [
    ({"machine": 3}, True),  # direct insertion: its consumer sets the pace
    ({"machine": 2, "belt": 1}, False),
    ({"belt": 2}, False),
    ({"other": 1}, False),
    ({"nothing": 1}, False),
    ({}, False),  # not reported: judged as before
])
def test_blocked_time_is_only_excused_for_a_machine_feeding_only_machines(unloads, passed):
    """User, 2026-10-12: under direct insertion an over-capacity machine shows as blocked, not idle."""
    v = judge(with_machines(machine({"working": 1620, "full_output": 1980}, unloads=unloads)))
    assert v.passed is passed, v.problems
    if passed:
        assert "machines: 1, none blocked on output; 1 feeding only machines, blocked up to 55.0%, not judged on it" \
            in v.summary


def test_unload_targets_are_parsed():
    data = {"build": {}, "outputs": [], "machines": [
        {"name": "electromagnetic-plant", "position": [4, 7], "working": 0.45, "unloads": {"machine": 3}},
        {"name": "electromagnetic-plant", "position": [9, 7], "working": 0.96, "unloads": {}}]}
    cable, circuit = parse_result(data).machines
    assert (cable.unloads, circuit.unloads) == ({"machine": 3}, {})


def test_output_under_98_percent_fails_even_when_every_machine_passes():
    idle = machine({"working": 2160, "no_ingredients": 1440})
    v = judge(with_machines(idle, idle, rate=14.0))
    assert v.problems == ["output iron-plate: 14.00/s is 93.3% of the 15/s target (needs >= 98%)"]


def test_output_growth_still_fails_a_working_machine():
    v = judge(with_machines(machine({"working": 3600}, output_growth=4)))
    assert v.problems == [
        "electric-furnace at (3.5, 1.5): output backing up, 4 more items waiting in it than when the window opened"]


def test_summary_reports_utilisation_by_kind():
    circuit = lambda working, x: MachineMeasure("electromagnetic-plant", (x, 2.0), working / 3600,
                                                {"working": working, "item_ingredient_shortage": 3600 - working},
                                                recipe="electronic-circuit", quality="legendary")
    cable = MachineMeasure("electromagnetic-plant", (2.0, 8.0), 0.73, {"working": 2628, "full_output": 36},
                           recipe="copper-cable", quality="legendary")
    furnace = machine({"working": 3600})
    r = with_machines(circuit(3456, 2.0), cable, circuit(3420, 6.0), furnace)
    v = judge(r)
    assert v.passed, v.problems
    assert v.summary[1:5] == [
        "machines: 4, most blocked on output 1.0% (electromagnetic-plant at (2, 8))",
        "utilisation legendary electromagnetic-plant (electronic-circuit) x2: working min 95.0% at (6, 2), "
        "mean 95.5%",
        "utilisation legendary electromagnetic-plant (copper-cable): working 73.0% at (2, 8)",
        "utilisation electric-furnace: working 100.0% at (3.5, 1.5)",
    ]
    (c, k, f) = utilisation(r.machines)
    assert (c.name, c.quality, c.recipe, c.count) == ("electromagnetic-plant", "legendary", "electronic-circuit", 2)
    assert (c.working_min, c.working_mean, c.lowest.position) == (0.95, pytest.approx(0.955), (6.0, 2.0))
    assert (k.count, k.working_min, f.recipe) == (1, 0.73, None)


def test_custom_thresholds():
    assert judge(make_result(rate=14.0), rate_min=0.9).passed
    blocked = with_machines(machine({"working": 3492, "full_output": 108}))  # 3%
    assert judge(blocked).passed and not judge(blocked, blocked_max=0.02).passed


def test_build_and_power_problems():
    v = judge(make_result(build=BuildStatus(2, 1, ["no loader fits at (6, 72)"]), power=PowerMeasure(False, 360, 1)))
    assert not v.passed
    assert v.problems == [
        "build error: no loader fits at (6, 72)",
        "build incomplete: 2 ghost(s) left unrevived",
        "build incomplete: 1 item request(s) left unfulfilled (modules not inserted)",
        "power: the harness power source isn't on the blueprint's electric network",
    ]
    assert "power: harness NOT linked, 360 unpowered machine-ticks, 1 other network(s)" in v.summary
    assert judge(make_result(power=PowerMeasure(None, 0, 0))).passed  # unreported link isn't a failure by itself


def test_shares_fall_back_on_the_tallied_ticks_when_the_window_is_unknown():
    r = with_machines(machine({"working": 900, "full_output": 100}, window=1000))
    assert judge(replace(r, ticks={"warmup": -1, "window": -1})).problems == [
        "electric-furnace at (3.5, 1.5): blocked on output 10.0% of the window (needs <= 5%), mostly full_output"]


def test_a_belt_only_result_is_judged_on_the_sink_rate():
    """No machine makes the item (produced_rate absent) and no pole to link (harness_linked None): both fine."""
    r = make_result(rate=240.0, target=240.0, machines=[], power=PowerMeasure(None, 0, 0))
    v = judge(r)
    assert v.passed, v.problems
    assert v.summary[:3] == ["iron-plate: 240.00/s of 240/s (100.0%); delivered 240.00/s, lanes 120.00/120.00",
                             "machines: none measured", "power: harness not linked (no blueprint pole), 0 unpowered "
                             "machine-ticks"]
    assert not judge(make_result(rate=230.0, target=240.0, machines=[])).passed


def test_zero_target_and_no_outputs_are_problems_not_crashes():
    v = judge(make_result(target=0))
    assert v.problems == ["output iron-plate: no positive target rate to judge 15.00/s against (target 0)"]
    assert "iron-plate: 15.00/s of 0/s (no target); delivered 15.00/s, lanes 7.50/7.50" in v.summary
    v = judge(make_result(outputs=[], machines=[]))
    assert v.problems == ["no output was measured, so throughput can't be judged"]
    assert "machines: none measured" in v.summary


def with_crafted(produced: float, delivered: float, target: float = 3.0) -> HarnessResult:
    r = make_result(rate=delivered, target=target)
    return replace(r, outputs=[replace(r.outputs[0], item="steel-plate", produced_rate=produced)])


def test_bar_uses_the_crafted_rate_not_the_aliased_sink_count():
    # Steel furnaces finish in step, so a window can catch an extra craft per furnace: 3.3/s at the sink.
    v = judge(with_crafted(produced=3.0, delivered=3.3))
    assert v.passed
    assert v.summary[0] == "steel-plate: 3.00/s of 3/s (100.0%); crafted 3.00/s, delivered 3.30/s, lanes 1.65/1.65"
    v = judge(with_crafted(produced=2.9, delivered=3.3))
    assert v.problems == ["output steel-plate: 2.90/s is 96.7% of the 3/s target (needs >= 98%)"]


def test_crafted_items_must_reach_the_output_port():
    v = judge(with_crafted(produced=3.0, delivered=2.0))
    assert v.problems == ["output steel-plate: only 2.00/s of the 3.00/s crafted reached the output port"]
    assert judge(with_crafted(produced=3.0, delivered=2.4)).passed  # 80% is the delivery floor, inclusive


def test_crafted_rate_and_machine_crafts_are_parsed():
    data = load_fixture()
    data["outputs"][0]["produced_rate"] = 15
    data["machines"][0].update(recipe="iron-plate", crafts=187.5)
    r = parse_result(data, IRON_PORTS)
    assert r.outputs[0].produced_rate == 15.0
    assert (r.machines[0].recipe, r.machines[0].crafts) == ("iron-plate", 187.5)
    assert parse_result(load_fixture(), IRON_PORTS).outputs[0].produced_rate is None


def test_machine_quality_speed_and_productivity_are_parsed():
    data = load_fixture()
    data["machines"][0].update(quality="legendary", crafting_speed=32.5, productivity=1.75)
    r = parse_result(data, IRON_PORTS)
    m = r.machines[0]
    assert (m.quality, m.crafting_speed, m.productivity) == ("legendary", 32.5, 1.75)
    assert (r.machines[1].quality, r.machines[1].crafting_speed, r.machines[1].productivity) == (None, None, None)


def test_a_machine_whose_output_piles_up_is_backing_up_even_while_working():
    r = make_result()
    grown = lambda n: replace(r, machines=[replace(r.machines[0], output_growth=n)])
    assert judge(grown(3)).passed  # an inserter hand's worth is noise
    assert judge(grown(4)).problems == [
        "electric-furnace at (3.5, 1.5): output backing up, 4 more items waiting in it than when the window opened"]


# --- server --------------------------------------------------------------------------------------------------

def test_missing_server_is_unavailable(tmp_path, monkeypatch):
    missing = tmp_path / "nope" / "factorio"
    with pytest.raises(HarnessUnavailable, match="no Factorio headless server at .*BPS_FACTORIO_SERVER"):
        find_server(missing)
    monkeypatch.setenv("BPS_FACTORIO_SERVER", str(missing))
    with pytest.raises(HarnessUnavailable, match=str(missing)):
        find_server()


def test_wrong_version_is_unavailable(tmp_path):
    fake = write_script(tmp_path / "factorio", 'echo "Version: 1.1.110 (build 60000, linux64, headless)"\n')
    with pytest.raises(HarnessUnavailable, match="is Factorio 1.1.110, the harness needs 2.0.77"):
        find_server(fake)


def test_broken_or_unrunnable_server_is_unavailable(tmp_path):
    crash = write_script(tmp_path / "crash", "echo 'cannot load libGL' >&2\nexit 127\n")
    with pytest.raises(HarnessUnavailable, match="exit 127"):
        find_server(crash)
    plain = tmp_path / "plain"
    plain.write_text("not a program")
    with pytest.raises(HarnessUnavailable, match="can't run"):
        find_server(plain)


def test_right_version_is_found_via_env_var(tmp_path, monkeypatch):
    fake = write_script(tmp_path / "factorio", f'echo "{GOOD_VERSION}"\n')
    monkeypatch.setenv("BPS_FACTORIO_SERVER", str(fake))
    assert find_server() == fake
    fake.write_text("#!/bin/sh\nexit 1\n")  # the check is cached per path for the process
    assert find_server(fake) == fake


# --- run() against a fake server -----------------------------------------------------------------------------

FAKE_SERVER = f"""\
import json, os, pathlib, sys
args = sys.argv[1:]
if args == ["--version"]:
    print({GOOD_VERSION!r}); sys.exit(0)
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
cfg = pathlib.Path(args[args.index("-c") + 1]).read_text()
write = pathlib.Path(cfg.split("write-data=")[1].strip())
step = "create" if "--create" in args else "benchmark"
if os.environ.get("FAKE_FAIL") == step:
    print("Error: boom in " + step); sys.exit(3)
if step == "create":
    pathlib.Path(args[args.index("--create") + 1]).write_text("save")
elif os.environ.get("FAKE_RESULT"):
    (write / "script-output").mkdir(parents=True)
    (write / "script-output" / "bps-result.json").write_text(pathlib.Path(os.environ["FAKE_RESULT"]).read_text())
"""


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "MOD_DIR", fake_mod(tmp_path))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("FAKE_RESULT", str(FIXTURES / "iron_15.json"))
    monkeypatch.delenv("FAKE_FAIL", raising=False)
    return write_script(tmp_path / "factorio", FAKE_SERVER, shebang=sys.executable)


def calls(tmp_path) -> list[list[str]]:
    return [json.loads(line) for line in (tmp_path / "calls.log").read_text().splitlines()]


def test_run_creates_then_benchmarks_and_cleans_up(tmp_path, fake_server):
    runs = tmp_path / "runs"
    r = harness.run("0eNqabc", IRON_PORTS, warmup_ticks=7200, server=fake_server, tmp_root=runs)
    assert r.outputs[0].rate == 15.0 and judge(r).passed
    assert set(r.wall) == {"create", "benchmark"} and all(t >= 0 for t in r.wall.values())
    create, bench = calls(tmp_path)
    assert create[:2] == ["-c", create[1]] and create[1].endswith("config.ini")
    assert create[2] == "--mod-directory" and create[4] == "--create" and create[5].endswith("save.zip")
    assert bench[4:] == ["--benchmark", create[5], "--benchmark-ticks", "10802"]
    assert "--disable-audio" not in create + bench
    assert list(runs.iterdir()) == []  # removed after a good run


def test_run_keeps_the_dir_on_request(tmp_path, fake_server):
    r = harness.run("0eNqabc", IRON_PORTS, warmup_ticks=7200, server=fake_server, tmp_root=tmp_path / "runs",
                    keep_dir=True)
    assert r.run_dir is not None and r.run_dir.parent == tmp_path / "runs"
    job = (r.run_dir / "mods" / "bps-harness_0.3.1" / "job.lua").read_text()
    assert "blueprint = [[0eNqabc]]" in job and "warmup_ticks = 7200" in job


@pytest.mark.parametrize("step", ["create", "benchmark"])
def test_failed_step_raises_with_output_tail_and_keeps_the_dir(tmp_path, fake_server, monkeypatch, step):
    monkeypatch.setenv("FAKE_FAIL", step)
    with pytest.raises(HarnessError) as e:
        harness.run("0eNqabc", IRON_PORTS, warmup_ticks=60, server=fake_server, tmp_root=tmp_path / "runs")
    msg = str(e.value)
    assert f"{step} exited with 3" in msg and f"Error: boom in {step}" in msg
    kept = next((tmp_path / "runs").iterdir())
    assert str(kept) in msg and (kept / "config.ini").is_file()


def test_missing_result_file_raises(tmp_path, fake_server, monkeypatch):
    monkeypatch.delenv("FAKE_RESULT")
    with pytest.raises(HarnessError, match="wrote no script-output/bps-result.json"):
        harness.run("0eNqabc", IRON_PORTS, warmup_ticks=7200, server=fake_server, tmp_root=tmp_path / "runs")


def test_run_rejects_bad_ticks_before_touching_the_server(tmp_path):
    with pytest.raises(ValueError):
        harness.run("0eN", IRON_PORTS, warmup_ticks=60, window_ticks=0, server=tmp_path / "missing")
