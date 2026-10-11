"""blueprint-smith build SPEC.json [--evaluate] | evaluate SPEC.json | decode STRING | types | install-server

Exit codes: 0 ok, 1 failed validation or the harness verdict, 2 bad spec, 3 the harness couldn't run."""
import argparse
import json
import sys

from draftsman.utils import string_to_JSON

from . import generators, harness
from .errors import BuildError, SpecError
from .evaluate import evaluate
from .pipeline import BuildResult, build


def _load_spec(path: str):
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SpecError(f"can't read {path}: {e}") from None


def _build(path: str) -> BuildResult | int:
    """The built spec, or the exit code if it failed."""
    try:
        result = build(_load_spec(path))
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
    return result


def _judge(result: BuildResult, args, out) -> int:
    """Run `result` in the headless harness and print the verdict to `out`; the exit code."""
    try:
        ev = evaluate(result, research=args.research, keep_dir=args.keep_run)
    except harness.HarnessUnavailable as e:
        print(f"harness unavailable: {e}", file=sys.stderr)
        return 3
    except harness.HarnessError as e:
        print(f"harness run failed: {e}", file=sys.stderr)
        return 3
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
    result = _build(args.spec)
    if isinstance(result, int):
        return result
    if args.evaluate and (code := _judge(result, args, sys.stderr)):
        return code
    if args.output:
        with open(args.output, "w") as f:
            f.write(result.string + "\n")
    else:
        print(result.string)
    return 0


def _cmd_evaluate(args) -> int:
    result = _build(args.spec)
    return result if isinstance(result, int) else _judge(result, args, sys.stdout)


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
    p.add_argument("--research", choices=("none", "all"), default="none",
                   help="technology state in the harness (default none: base stats, as the ratio math assumes)")
    p.add_argument("--keep-run", action="store_true", help="keep the harness run directory for inspection")


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
