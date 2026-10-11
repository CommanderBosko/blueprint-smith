"""`blueprint-smith evaluate` / `build --evaluate`: exit codes 0 pass, 1 harness verdict failed, 2 bad spec, 3 no harness."""
import json

import pytest

from blueprint_smith import cli, harness
from blueprint_smith.evaluate import Evaluation
from blueprint_smith.harness import BuildStatus, HarnessResult, OutputMeasure, PowerMeasure, Verdict


def _spec(tmp_path, spec: dict) -> str:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return str(path)


def _fake_evaluate(passed: bool):
    def evaluate(built, **_):
        result = HarnessResult(build=BuildStatus(0, 0, []), ticks={"warmup": 1, "window": 1},
                               outputs=[OutputMeasure("iron-plate", 15.0, 900, 15.0, [7.5, 7.5])], machines=[],
                               power=PowerMeasure(True, 0, 0), series=[], wall={}, raw={})
        problems = [] if passed else ["output iron-plate: too slow"]
        return Evaluation(Verdict(passed, problems, ["iron-plate: 15.00/s of 15/s"]), result, 1, 1)
    return evaluate


@pytest.mark.parametrize("passed, code", [(True, 0), (False, 1)])
def test_evaluate_exit_code_follows_the_verdict(tmp_path, monkeypatch, capsys, passed, code):
    monkeypatch.setattr(cli, "evaluate", _fake_evaluate(passed))
    assert cli.main(["evaluate", _spec(tmp_path, {"type": "smelting_column", "count": 2})]) == code
    out, err = capsys.readouterr()
    assert "harness: iron-plate: 15.00/s of 15/s" in out
    assert ("too slow" in err) == (not passed)


def test_build_evaluate_withholds_the_string_on_a_failed_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "evaluate", _fake_evaluate(False))
    assert cli.main(["build", _spec(tmp_path, {"type": "smelting_column", "count": 2}), "--evaluate"]) == 1
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(cli, "evaluate", _fake_evaluate(True))
    assert cli.main(["build", _spec(tmp_path, {"type": "smelting_column", "count": 2}), "--evaluate"]) == 0
    assert capsys.readouterr().out.startswith("0e")


def test_evaluate_without_a_server_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BPS_FACTORIO_SERVER", str(tmp_path / "missing" / "factorio"))
    assert cli.main(["evaluate", _spec(tmp_path, {"type": "smelting_column", "count": 2})]) == 3
    assert "blueprint-smith install-server" in capsys.readouterr().err


def test_evaluate_bad_spec_exits_2(tmp_path):
    assert cli.main(["evaluate", _spec(tmp_path, {"type": "nope"})]) == 2


@pytest.mark.harness
def test_overloaded_column_fails_in_the_real_harness(tmp_path, capsys):
    """30 furnaces want 18.75 ore/s, but a yellow belt carries 15/s: the bottom 6 starve."""
    try:
        harness.find_server()
    except harness.HarnessUnavailable as e:
        pytest.skip(f"no headless server: {e}")
    assert cli.main(["evaluate", _spec(tmp_path, {"type": "smelting_column", "count": 30})]) == 1
    out, err = capsys.readouterr()
    assert "iron-plate: 15.00/s of 18.75/s (80.0%)" in out
    assert err.count("mostly no_ingredients") == 6
