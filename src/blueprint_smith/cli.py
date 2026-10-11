"""blueprint-smith build SPEC.json | decode STRING | types"""
import argparse
import json
import sys

from draftsman.utils import string_to_JSON

from . import generators
from .errors import BuildError, SpecError
from .pipeline import build


def _load_spec(path: str):
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SpecError(f"can't read {path}: {e}") from None


def _cmd_build(args) -> int:
    try:
        result = build(_load_spec(args.spec))
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
    if args.output:
        with open(args.output, "w") as f:
            f.write(result.string + "\n")
    else:
        print(result.string)
    return 0


def _cmd_decode(args) -> int:
    s = open(args.string[1:]).read() if args.string.startswith("@") else args.string
    print(json.dumps(string_to_JSON(s.strip()), indent=2))
    return 0


def _cmd_types(_args) -> int:
    print("\n".join(sorted(generators.REGISTRY)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="blueprint-smith")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a blueprint string from a JSON spec ('-' for stdin)")
    b.add_argument("spec")
    b.add_argument("-o", "--output", help="write the string to a file instead of stdout")
    b.set_defaults(fn=_cmd_build)
    d = sub.add_parser("decode", help="print a blueprint string as JSON (STRING or @file)")
    d.add_argument("string")
    d.set_defaults(fn=_cmd_decode)
    t = sub.add_parser("types", help="list available blueprint types")
    t.set_defaults(fn=_cmd_types)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
