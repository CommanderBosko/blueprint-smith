#!/usr/bin/env bash
# Build a blueprint for an in-game test, check that it decodes, and copy it to the clipboard.
#
# Usage: handoff.sh SPEC OUTDIR [none|all]
#   SPEC       spec JSON path (absolute, or relative to the caller's cwd)
#   OUTDIR     where <spec-stem>.txt (the string) and <spec-stem>.log (notes) go:
#              the session scratchpad, never $TMPDIR (unset here)
#   none|all   harness research state (default: the one the spec's type registers, e.g. all for
#              circuit_block, none for the furnace columns); pass it only to override that
#
# Prints HARNESS:, BLUEPRINT:, ENTITIES:, FILE: and CLIPBOARD: lines on stdout, plus the
# build notes and harness verdict on stderr. It never prints the blueprint string itself.
# Exit: 0 built, decoded and copied; 1 failed validation or the harness verdict; 2 bad spec;
#       4 built and decoded but the clipboard copy failed; 5 the string didn't decode; 64 usage.
set -uo pipefail

usage() { echo "usage: handoff.sh SPEC OUTDIR [none|all]" >&2; exit 64; }
[ $# -ge 2 ] && [ $# -le 3 ] || usage
[ -n "$1" ] && [ -n "$2" ] || usage   # an empty OUTDIR is the unset-$TMPDIR slip
research="${3:-}"
case "$research" in ""|none|all) ;; *) usage ;; esac
research_args=()
[ -n "$research" ] && research_args=(--research "$research")

spec="$(realpath -- "$1")" || exit 2
mkdir -p -- "$2" || exit 64
outdir="$(realpath -- "$2")" || exit 64
stem="$(basename -- "$spec" .json)"
out="$outdir/$stem.txt"
log="$outdir/$stem.log"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)" || exit 64
cd -- "$root" || exit 64
bps=.venv/bin/blueprint-smith

rm -f -- "$out"   # never hand off a stale string from an earlier run

"$bps" build "$spec" --evaluate "${research_args[@]}" -o "$out" 2>"$log"
code=$?
cat -- "$log" >&2
case $code in
  0)
    echo "HARNESS: passed (research ${research:-as the type registers})"
    ;;
  3)
    echo "HARNESS: skipped (the harness couldn't run); fell back to a static build"
    "$bps" build "$spec" -o "$out" 2>/dev/null || {
      code=$?
      echo "BUILD: static build failed (exit $code); not handing off"
      rm -f -- "$out"
      exit "$code"
    }
    ;;
  *)
    echo "BUILD: failed (exit $code: 1 = failed validation or the harness verdict, 2 = bad spec); not handing off"
    rm -f -- "$out"
    exit "$code"
    ;;
esac

"$bps" decode "@$out" | .venv/bin/python -I -c '
import collections, json, sys
d = json.load(sys.stdin)
bp = d.get("blueprint")
if bp is None:
    sys.exit("not a single blueprint; top-level keys: " + ", ".join(d))
ents = bp.get("entities", [])
print("BLUEPRINT: label=%r entities=%d wires=%d" % (bp.get("label"), len(ents), len(bp.get("wires", []))))
counts = collections.Counter(e["name"] for e in ents).most_common()
print("ENTITIES: " + ", ".join("%d %s" % (n, name) for name, n in counts))
' || { echo "DECODE: failed; not handing off"; exit 5; }
echo "FILE: $out"

if command -v wl-copy >/dev/null 2>&1 && wl-copy < "$out" 2>/dev/null \
  && [ "$(wl-paste -n 2>/dev/null | head -c 40)" = "$(head -c 40 -- "$out")" ]; then
  echo "CLIPBOARD: copied (wl-copy, read back OK)"
else
  echo "CLIPBOARD: failed; give the user: ! wl-copy < $out"
  exit 4
fi
