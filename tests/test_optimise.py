"""The optimiser (M2 piece F): variants -> builds -> ranked by footprint, then power -> harness best-first in batches.

A toy generator (a straight turbo belt of `length` tiles, so its footprint is length x 1) and a fake harness keep
these off the real server; the real end-to-end run is the parent's (docs/m2-plan.md, verification step 7)."""
import json
from types import SimpleNamespace

import pytest
from draftsman.entity import new_entity

from blueprint_smith import cli, generators
from blueprint_smith import optimise as opt
from blueprint_smith.errors import SpecError
from blueprint_smith.generators import Port
from blueprint_smith.pipeline import build

BELT = "turbo-transport-belt"
EAST = 4
ITEM = "iron-plate"


def toy_line(spec: dict):
    """`length` belts flowing east, input at the west end, output at the east end. `blocked` puts a belt past the
    output end, which pipeline.check_ports rejects."""
    n = spec["length"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise SpecError(f"'length' must be a positive integer, got {n!r}")
    entities = [new_entity(BELT, tile_position=(x, 0), direction=EAST) for x in range(n + bool(spec.get("blocked")))]
    ports = [Port("input", ITEM, BELT, (0, 0), EAST, 60.0), Port("output", ITEM, BELT, (n - 1, 0), EAST, 60.0)]
    return entities, [f"toy line of {n}"], ports


def _register(monkeypatch, specs, research="none"):
    """Make `toy_line` the only type with variants; it offers `specs` (a length alone means {"length": n})."""
    specs = [s if isinstance(s, dict) else {"type": "toy_line", "length": s} for s in specs]
    requests = []

    def variants(request):
        requests.append(request)
        return iter(specs) if request["item"] == ITEM else iter(())

    monkeypatch.setitem(generators.REGISTRY, "toy_line", toy_line)
    monkeypatch.setitem(generators.CHECKS, "toy_line", ())
    monkeypatch.setitem(generators.RESEARCH, "toy_line", research)
    monkeypatch.setattr(generators, "VARIANTS", {"toy_line": variants})
    return requests


class FakeHarness:
    """Passes every line except those whose length is in `failing`; records (length, research, keep_dir) per run."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.calls = []

    def __call__(self, built, *, research, keep_dir):
        n = len(built.blueprint.entities)
        self.calls.append((n, research, keep_dir))
        passed = n not in self.failing
        problems = [] if passed else [f"output {ITEM}: line of {n} too slow"]
        verdict = SimpleNamespace(passed=passed, problems=problems, summary=[f"{ITEM}: line of {n}"])
        return SimpleNamespace(verdict=verdict, result=SimpleNamespace(run_dir=None))

    @property
    def lengths(self):
        return sorted(n for n, _, _ in self.calls)


REQUEST = {"item": ITEM, "rate": 60}


def _length(c: opt.Candidate) -> int:
    return c.spec["length"]


def test_picks_the_smallest_passing_footprint(monkeypatch):
    _register(monkeypatch, [5, 3, 4, 2])
    fake = FakeHarness()
    found = opt.optimise(REQUEST, evaluator=fake, jobs=1)
    w = found.winner
    assert (_length(w), w.width, w.height, w.tiles) == (2, 2, 1, 2)
    assert [_length(c) for c in found.candidates] == [2, 3, 4, 5]
    assert found.runs == 1 and fake.lengths == [2]
    assert w.evaluation.verdict.passed and found.candidates[1].evaluation is None
    assert found.rejected == [] and found.variants == 4


def test_a_variant_the_harness_fails_is_passed_over(monkeypatch):
    _register(monkeypatch, [5, 3, 4, 2])
    found = opt.optimise(REQUEST, evaluator=FakeHarness(failing={2}), jobs=1)
    assert _length(found.winner) == 3
    smallest = found.candidates[0]
    assert _length(smallest) == 2 and not smallest.evaluation.verdict.passed
    assert found.runs == 2


def test_power_breaks_a_footprint_tie(monkeypatch):
    # "a" sorts first by JSON, so only the power can put "b" ahead
    _register(monkeypatch, [{"type": "toy_line", "length": 3, "label": label} for label in ("a", "b")])
    monkeypatch.setattr(opt, "power_estimate", lambda bp, research: {"a": 2e6, "b": 1e6}[bp.label])
    found = opt.optimise(REQUEST, evaluator=FakeHarness(), jobs=1)
    assert found.winner.spec["label"] == "b" and found.winner.power == 1e6
    assert [c.spec["label"] for c in found.candidates] == ["b", "a"]
    assert found.runs == 1


def test_equal_footprint_and_power_rank_by_spec(monkeypatch):
    _register(monkeypatch, [{"type": "toy_line", "length": 3, "label": label} for label in ("b", "a")])
    found = opt.optimise(REQUEST, evaluator=FakeHarness(), jobs=1)
    assert [c.spec["label"] for c in found.candidates] == ["a", "b"]


@pytest.mark.parametrize("jobs, failing, runs, winner", [
    (1, {2}, [2, 3], 3),
    (2, {2}, [2, 3], 3),
    (2, {2, 3}, [2, 3, 4, 5], 4),
    (4, {2}, [2, 3, 4, 5], 3),  # 4 and 5 pass in the same batch, but 3 ranks above them
    (8, {2}, [2, 3, 4, 5, 6], 3),
])
def test_batches_stop_once_one_holds_a_pass(monkeypatch, jobs, failing, runs, winner):
    _register(monkeypatch, [2, 3, 4, 5, 6])
    fake = FakeHarness(failing)
    found = opt.optimise(REQUEST, evaluator=fake, jobs=jobs)
    assert fake.lengths == runs and found.runs == len(runs)
    assert _length(found.winner) == winner
    assert [_length(c) for c in found.candidates if c.evaluation is not None] == runs


@pytest.mark.parametrize("jobs, max_runs, runs", [(2, 3, [2, 3, 4]), (4, 1, [2]), (1, 0, [])])
def test_max_runs_caps_the_harness_runs(monkeypatch, jobs, max_runs, runs):
    _register(monkeypatch, [2, 3, 4, 5])
    fake = FakeHarness(failing={2, 3, 4, 5})
    found = opt.optimise(REQUEST, evaluator=fake, jobs=jobs, max_runs=max_runs)
    assert fake.lengths == runs and found.runs == len(runs)
    assert found.winner is None


def test_nothing_passing_means_no_winner(monkeypatch):
    _register(monkeypatch, [2, 3])
    found = opt.optimise(REQUEST, evaluator=FakeHarness(failing={2, 3}), jobs=1)
    assert found.winner is None and found.runs == 2


def test_an_item_no_generator_makes_is_a_spec_error(monkeypatch):
    _register(monkeypatch, [2])
    with pytest.raises(SpecError, match="no generator makes 5 copper-plate/s.*toy_line"):
        opt.optimise({"item": "copper-plate", "rate": 5}, evaluator=FakeHarness())


@pytest.mark.parametrize("request_", [
    None, [], "iron-plate",
    {"rate": 60}, {"item": 7, "rate": 60}, {"item": "", "rate": 60},
    {"item": ITEM}, {"item": ITEM, "rate": 0}, {"item": ITEM, "rate": -1}, {"item": ITEM, "rate": True},
    {"item": ITEM, "rate": "60"}, {"item": ITEM, "rate": float("nan")}, {"item": ITEM, "rate": float("inf")},
])
def test_a_bad_request_is_a_spec_error(monkeypatch, request_):
    _register(monkeypatch, [2])
    fake = FakeHarness()
    with pytest.raises(SpecError):
        opt.optimise(request_, evaluator=fake)
    assert fake.calls == []


def test_other_request_keys_reach_the_variants(monkeypatch):
    requests = _register(monkeypatch, [2])
    opt.optimise({**REQUEST, "quality": "rare"}, evaluator=FakeHarness())
    assert requests == [{**REQUEST, "quality": "rare"}]


def test_a_spec_that_fails_to_build_is_rejected_not_fatal(monkeypatch):
    bad = [
        {"type": "toy_line", "length": 1, "blocked": True},  # BuildError: the output end is blocked
        {"type": "toy_line", "length": 0},  # SpecError from the generator
        {"type": "no_such_type"},  # SpecError from the registry
    ]
    _register(monkeypatch, [*bad, 3, 2])
    found = opt.optimise(REQUEST, evaluator=FakeHarness(), jobs=1)
    assert _length(found.winner) == 2
    assert [spec for spec, _ in found.rejected] == bad
    reasons = [why for _, why in found.rejected]
    assert "output port" in reasons[0] and "length" in reasons[1] and "no_such_type" in reasons[2]
    assert found.variants == 5 and len(found.candidates) == 2


def test_duplicate_variants_run_once(monkeypatch):
    _register(monkeypatch, [3, {"length": 3, "type": "toy_line"}, 4])
    fake = FakeHarness(failing={3})
    found = opt.optimise(REQUEST, evaluator=fake, jobs=1)
    assert found.variants == 2 and fake.lengths == [3, 4]


@pytest.mark.parametrize("research", ["none", "all"])
def test_research_comes_from_the_type(monkeypatch, research):
    _register(monkeypatch, [2, 3], research=research)
    fake = FakeHarness(failing={2})
    opt.optimise(REQUEST, evaluator=fake, jobs=2, keep_dir=True)
    assert [(r, k) for _, r, k in fake.calls] == [(research, True)] * 2


def test_the_default_evaluator_is_evaluate(monkeypatch):
    _register(monkeypatch, [2])
    fake = FakeHarness()
    monkeypatch.setattr(opt, "evaluate", fake)
    assert _length(opt.optimise(REQUEST).winner) == 2
    assert fake.calls == [(2, "none", False)]


def test_harness_errors_propagate(monkeypatch):
    from blueprint_smith import harness
    _register(monkeypatch, [2, 3])

    def unavailable(built, **_):
        raise harness.HarnessUnavailable("no server")

    with pytest.raises(harness.HarnessUnavailable):
        opt.optimise(REQUEST, evaluator=unavailable, jobs=2)


# --- footprint and power on the real circuit block ---------------------------------------------------------------
def test_footprint_of_the_default_circuit_block_is_13_by_11():
    """Bounding box AABB(-6.9, -4.7, 5.9, 5.9): collision boxes sit inside their tiles, so the edges round out."""
    assert opt.footprint(build({"type": "circuit_block"}).blueprint) == (13, 11)


def test_footprint_counts_whole_tiles_of_the_belts(monkeypatch):
    _register(monkeypatch, [])
    assert opt.footprint(build({"type": "toy_line", "length": 4}).blueprint) == (4, 1)


def test_power_estimate_of_the_circuit_block_grows_with_an_inserter():
    base = opt.power_estimate(build({"type": "circuit_block"}).blueprint, "all")
    more = opt.power_estimate(build({"type": "circuit_block", "east_inserters": 3}).blueprint, "all")
    assert base > 0
    # the one extra legendary stack inserter is the whole difference
    assert more - base == pytest.approx(opt.inserter_power(new_entity("stack-inserter", quality="legendary")))
    assert more > base


@pytest.mark.parametrize("name, quality, watts", [
    ("stack-inserter", "normal", 1e3 + 60 * (40e3 * 0.04 + 40e3 * 0.1)),  # 337 kW
    ("stack-inserter", "legendary", 1e3 + 60 * (40e3 * 0.04 + 40e3 * 0.1) * 2.5),
    ("inserter", "normal", 0.4e3 + 60 * (5e3 * 0.014 + 5e3 * 0.035)),
    ("burner-inserter", "normal", 0.0),  # burns fuel, draws no power
])
def test_inserter_power_is_its_max_consumption(name, quality, watts):
    assert opt.inserter_power(new_entity(name, quality=quality)) == pytest.approx(watts)


def test_power_estimate_counts_furnaces_without_a_recipe():
    assert opt.power_estimate(build({"type": "smelting_column", "count": 2}).blueprint) > 0


# --- CLI ---------------------------------------------------------------------------------------------------------
def _request(tmp_path, request=REQUEST) -> str:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return str(path)


def test_cli_prints_the_winner_and_the_report(tmp_path, monkeypatch, capsys):
    _register(monkeypatch, [4, 2, 3])
    monkeypatch.setattr(cli, "evaluate", FakeHarness(failing={2}))
    assert cli.main(["optimise", _request(tmp_path), "--jobs", "1"]) == 0
    out, err = capsys.readouterr()
    assert out == build({"type": "toy_line", "length": 3}).string + "\n"
    assert "optimise: 3 variant(s), 0 rejected, 2 harness run(s)" in err
    lines = err.splitlines()
    assert any(line.startswith("  2x1 = 2 tiles, 0.00 MW, length=2: FAIL: output iron-plate: line of 2")
               for line in lines)
    assert "  3x1 = 3 tiles, 0.00 MW, length=3: PASS (chosen)" in lines
    assert "4x1" not in err  # never ran
    assert "harness: iron-plate: line of 3" in lines and "toy line of 3" in lines
    assert json.loads(err.split("chosen spec:\n")[1].split("\nharness:")[0]) == {"type": "toy_line", "length": 3}


def test_cli_writes_the_string_and_spec_to_files(tmp_path, monkeypatch, capsys):
    _register(monkeypatch, [3, 2])
    monkeypatch.setattr(cli, "evaluate", FakeHarness())
    out_file, spec_file = tmp_path / "bp.txt", tmp_path / "winner.json"
    assert cli.main(["optimise", _request(tmp_path), "-o", str(out_file), "--spec-out", str(spec_file)]) == 0
    assert capsys.readouterr().out == ""
    assert out_file.read_text() == build({"type": "toy_line", "length": 2}).string + "\n"
    assert json.loads(spec_file.read_text()) == {"type": "toy_line", "length": 2}


def test_cli_exits_1_when_nothing_passes(tmp_path, monkeypatch, capsys):
    _register(monkeypatch, [2, 3, 4])
    monkeypatch.setattr(cli, "evaluate", FakeHarness(failing={2, 3, 4}))
    spec_file = tmp_path / "winner.json"
    assert cli.main(["optimise", _request(tmp_path), "--max-runs", "2", "--spec-out", str(spec_file)]) == 1
    out, err = capsys.readouterr()
    assert out == "" and not spec_file.exists()
    assert "nothing passed the harness; 1 built variant(s) not run (--max-runs)" in err


@pytest.mark.parametrize("request_", [{"item": ITEM}, {"item": "copper-plate", "rate": 5}, "not json"])
def test_cli_exits_2_on_a_bad_request(tmp_path, monkeypatch, capsys, request_):
    _register(monkeypatch, [2])
    fake = FakeHarness()
    monkeypatch.setattr(cli, "evaluate", fake)
    path = tmp_path / "request.json"
    path.write_text(request_ if isinstance(request_, str) else json.dumps(request_))
    assert cli.main(["optimise", str(path)]) == 2
    assert "request error" in capsys.readouterr().err and fake.calls == []


def test_cli_exits_3_without_a_harness(tmp_path, monkeypatch, capsys):
    from blueprint_smith import harness
    _register(monkeypatch, [2])

    def unavailable(built, **_):
        raise harness.HarnessUnavailable("run blueprint-smith install-server")

    monkeypatch.setattr(cli, "evaluate", unavailable)
    assert cli.main(["optimise", _request(tmp_path)]) == 3
    assert "harness unavailable" in capsys.readouterr().err
