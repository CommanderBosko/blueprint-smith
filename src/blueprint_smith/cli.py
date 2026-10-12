"""blueprint-smith build SPEC.json [--evaluate] | evaluate SPEC.json | optimise REQUEST.json | decode STRING | types
| install-server

Exit codes: 0 ok, 1 failed validation or the harness verdict (optimise: no variant passed), 2 bad spec or request,
3 the harness couldn't run."""
import argparse
import json
import sys

from draftsman.utils import string_to_JSON

from . import generators, harness
from .errors import BuildError, SpecError
from .evaluate import evaluate
from .optimise import Optimised, optimise
from .pipeline import BuildResult, build


def _load_spec(path: str):
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SpecError(f"can't read {path}: {e}") from None


def _build(path: str) -> tuple[dict, BuildResult] | int:
    """The spec and its build, or the exit code if it failed."""
    try:
        spec = _load_spec(path)
        result = build(spec)
    except SpecError as e:
        print(f"spec error: {e}", file=sys.stderr)
        return 2
    except BuildError as e:
        print("build failed validation:", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    for n in result.notes:
        print(n, file=sys.stderr)
    return spec, result


def _harness_failed(e: Exception) -> int:
    if isinstance(e, harness.HarnessUnavailable):
        print(f"harness unavailable: {e}", file=sys.stderr)
    else:
        print(f"harness run failed: {e}", file=sys.stderr)
    return 3


def _judge(spec: dict, result: BuildResult, args, out) -> int:
    """Run `result` in the headless harness and print the verdict to `out`; the exit code. The research is the
    spec type's declared state (generators.RESEARCH) unless --research says otherwise."""
    research = args.research or generators.RESEARCH.get(spec["type"], "none")
    try:
        ev = evaluate(result, research=research, keep_dir=args.keep_run)
    except (harness.HarnessUnavailable, harness.HarnessError) as e:
        return _harness_failed(e)
    for line in ev.verdict.summary:
        print(f"harness: {line}", file=out)
    if ev.result.run_dir:
        print(f"harness: run kept in {ev.result.run_dir}", file=out)
    if not ev.verdict.passed:
        print("failed the harness verdict:", file=sys.stderr)
        for p in ev.verdict.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


def _cmd_build(args) -> int:
    built = _build(args.spec)
    if isinstance(built, int):
        return built
    spec, result = built
    if args.evaluate and (code := _judge(spec, result, args, sys.stderr)):
        return code
    if args.output:
        with open(args.output, "w") as f:
            f.write(result.string + "\n")
    else:
        print(result.string)
    return 0


def _cmd_evaluate(args) -> int:
    built = _build(args.spec)
    return built if isinstance(built, int) else _judge(*built, args, sys.stdout)


def _options(spec: dict) -> str:
    """A candidate's spec options, `type` left out: what tells the variants apart."""
    shown = [f"{k}={v if isinstance(v, str) else json.dumps(v)}" for k, v in spec.items() if k != "type"]
    return " ".join(shown) or "defaults"


def _report(found: Optimised) -> None:
    """What was tried and how it fared, on stderr: the stdout of `optimise` is the winner's string alone."""
    err = sys.stderr
    print(f"optimise: {found.variants} variant(s), {len(found.rejected)} rejected, {found.runs} harness run(s)",
          file=err)
    for spec, why in found.rejected:
        print(f"  rejected {json.dumps(spec, default=str)}: {why}", file=err)
    several = len({c.spec["type"] for c in found.candidates}) > 1
    for c in found.candidates:
        if c.evaluation is None:
            continue
        v = c.evaluation.verdict
        verdict = "PASS" if v.passed else f"FAIL: {v.problems[0] if v.problems else 'no problem given'}"
        chosen = " (chosen)" if c is found.winner else ""
        kind = f"{c.spec['type']} " if several else ""
        print(f"  {c.width}x{c.height} = {c.tiles} tiles, {c.power / 1e6:.2f} MW, {kind}{_options(c.spec)}: "
              f"{verdict}{chosen}", file=err)
        if c.evaluation.result.run_dir:
            print(f"    run kept in {c.evaluation.result.run_dir}", file=err)
    if found.winner is None:
        unrun = sum(c.evaluation is None for c in found.candidates)
        why = f"; {unrun} built variant(s) not run (--max-runs)" if unrun else ""
        print(f"nothing passed the harness{why}", file=err)
        return
    w = found.winner
    print("chosen spec:", file=err)
    print(json.dumps(w.spec, indent=2), file=err)
    for line in w.evaluation.verdict.summary:
        print(f"harness: {line}", file=err)
    for n in w.built.notes:
        print(n, file=err)


def _cmd_optimise(args) -> int:
    try:
        found = optimise(_load_spec(args.request), evaluator=evaluate, jobs=args.jobs, max_runs=args.max_runs,
                         keep_dir=args.keep_run)
    except SpecError as e:
        print(f"request error: {e}", file=sys.stderr)
        return 2
    except (harness.HarnessUnavailable, harness.HarnessError) as e:
        return _harness_failed(e)
    _report(found)
    if found.winner is None:
        return 1
    if args.spec_out:
        with open(args.spec_out, "w") as f:
            f.write(json.dumps(found.winner.spec, indent=2) + "\n")
    if args.output:
        with open(args.output, "w") as f:
            f.write(found.winner.built.string + "\n")
    else:
        print(found.winner.built.string)
    return 0


def _cmd_install_server(_args) -> int:
    print(harness.install_server())
    return 0


def _cmd_decode(args) -> int:
    s = open(args.string[1:]).read() if args.string.startswith("@") else args.string
    print(json.dumps(string_to_JSON(s.strip()), indent=2))
    return 0


def _cmd_types(_args) -> int:
    print("\n".join(sorted(generators.REGISTRY)))
    return 0


def _harness_options(p) -> None:
    p.add_argument("--research", choices=("none", "all"), default=None,
                   help="technology state in the harness (default: the one the spec's type declares, e.g. none "
                        "for the furnace columns' base stats, all for M2 blocks that need belt stacking)")
    p.add_argument("--keep-run", action="store_true", help="keep the harness run directory for inspection")


def _positive(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {n}")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="blueprint-smith")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a blueprint string from a JSON spec ('-' for stdin)")
    b.add_argument("spec")
    b.add_argument("-o", "--output", help="write the string to a file instead of stdout")
    b.add_argument("--evaluate", action="store_true", help="also run it in the headless harness; fail on its verdict")
    _harness_options(b)
    b.set_defaults(fn=_cmd_build)
    e = sub.add_parser("evaluate", help="build a spec and run it in the headless harness (verdict on stdout)")
    e.add_argument("spec")
    _harness_options(e)
    e.set_defaults(fn=_cmd_evaluate)
    o = sub.add_parser("optimise", help="find the smallest blueprint that passes the headless harness for a "
                                        "request such as {\"item\": \"electronic-circuit\", \"rate\": 240} "
                                        "('-' for stdin); report on stderr, string on stdout")
    o.add_argument("request")
    o.add_argument("-o", "--output", help="write the winner's string to a file instead of stdout")
    o.add_argument("--spec-out", metavar="FILE", help="write the winner's spec to a file as JSON")
    o.add_argument("--jobs", type=_positive, help="harness runs at once (default: the CPU count, at most 8)")
    o.add_argument("--max-runs", type=_positive, help="stop after this many harness runs, passed or not")
    o.add_argument("--keep-run", action="store_true", help="keep every harness run directory for inspection")
    o.set_defaults(fn=_cmd_optimise)
    i = sub.add_parser("install-server", help=f"download the Factorio {harness.REQUIRED_VERSION} headless server")
    i.set_defaults(fn=_cmd_install_server)
    d = sub.add_parser("decode", help="print a blueprint string as JSON (STRING or @file)")
    d.add_argument("string")
    d.set_defaults(fn=_cmd_decode)
    t = sub.add_parser("types", help="list available blueprint types")
    t.set_defaults(fn=_cmd_types)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
