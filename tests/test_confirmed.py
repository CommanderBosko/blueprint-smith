"""Golden snapshots of every layout confirmed in-game (CLAUDE.md Status, docs/techniques.md), entity for entity.

The property tests check what a layout must do. These pin what the user actually ran, so a refactor that moves one
belt of a confirmed blueprint fails even when every property still holds. Each fixture in fixtures/confirmed/ is
self-contained:
- the spec, embedded rather than read from examples/, so editing an example can't move the goalposts;
- a line citing where its in-game test is recorded;
- the full pipeline's layout, P3 labels and P4 balancers included: `entities` and `wires`, one a line.

No headless server needed. After an intended change, `BPS_UPDATE_SNAPSHOTS=1 .venv/bin/pytest -q
tests/test_confirmed.py` rewrites each fixture's layout and keeps its spec and citation. Then re-test the block
in-game and update docs/techniques.md.
"""
import json
import os
from collections import Counter
from pathlib import Path

import pytest
from draftsman.constants import Direction

from blueprint_smith import generators
from blueprint_smith.pipeline import LABEL, build

FIXTURES = Path(__file__).parent / "fixtures" / "confirmed"
FILES = sorted(FIXTURES.glob("*.json"))
UPDATE = "BPS_UPDATE_SNAPSHOTS"
OWN = ("spec", "confirmed")  # a fixture's keys that aren't layout
METADATA = {"item", "version", "label", "description", "icons"}  # nor are these blueprint keys
MAX_LINES = 20
HINT = ("the layout changed vs the in-game-confirmed snapshot; if intended, rerun with BPS_UPDATE_SNAPSHOTS=1, "
        "re-test it in-game, and update docs/techniques.md")


# --- normalising and comparing ----------------------------------------------------------------------------------

def _order(e: dict) -> tuple:
    return e["position"]["y"], e["position"]["x"], e["name"]


def layout(bp) -> dict:
    """`bp`'s layout, whatever order its entities were created in:
    - `entities`: each entity's dict without entity_number, sorted by position (row by row), then name;
    - `wires`: each end as [name, x, y, connector] instead of an entity number, ends and wires sorted;
    - any other blueprint key that isn't metadata, as is.
    JSON-normalised, so it compares equal to a fixture's."""
    data = bp.to_dict()["blueprint"]
    numbered = {e["entity_number"]: e for e in data.get("entities", [])}
    entities = sorted(({k: v for k, v in e.items() if k != "entity_number"} for e in numbered.values()), key=_order)

    def end(number, connector):
        e = numbered[number]
        return [e["name"], e["position"]["x"], e["position"]["y"], connector]

    wires = sorted(sorted([end(a, ca), end(b, cb)]) for a, ca, b, cb in data.get("wires", []))
    out = {"entities": entities, "wires": wires}
    out.update((k, v) for k, v in data.items() if k not in METADATA and k not in out)
    return json.loads(json.dumps(out))


def _canon(item) -> str:
    return json.dumps(item, sort_keys=True)


def _items(value) -> list:
    return [] if value is None else value if isinstance(value, list) else [value]


def _minus(a: list, b: list) -> list:
    """The items of `a` not matched one for one in `b` (a multiset difference)."""
    left = Counter(map(_canon, b))
    out = []
    for item in a:
        if left[c := _canon(item)]:
            left[c] -= 1
        else:
            out.append(item)
    return out


def _clip(text: str, n: int = 100) -> str:
    return text if len(text) <= n else text[:n - 3] + "..."


def _where(e: dict) -> str:
    return f"{e['name']} at ({e['position']['x']:g}, {e['position']['y']:g})"


def _rest(e: dict) -> str:
    rest = {k: v for k, v in e.items() if k not in ("name", "position")}
    return f": {_clip(_canon(rest))}" if rest else ""


def _field(e: dict, key: str) -> str:
    return _clip(_canon(e[key]), 60) if key in e else "(none)"


def _entity_lines(gone: list, came: list) -> list[str]:
    """A line an entity, in position order so a moved entity's two lines sit together: '~' for one whose name and
    position match but whose other fields changed, '-' for one only in the snapshot, '+' for one only in the build."""
    def key(e):
        return e["name"], e["position"]["x"], e["position"]["y"]

    pending: dict[tuple, list] = {}
    for e in came:
        pending.setdefault(key(e), []).append(e)
    rows = []
    for old in gone:
        if pending.get(key(old)):
            new = pending[key(old)].pop(0)
            fields = "; ".join(f"{k} {_field(old, k)} -> {_field(new, k)}"
                               for k in sorted(old.keys() | new.keys()) if old.get(k) != new.get(k))
            rows.append((_order(old), f"~ {_where(old)}: {fields}"))
        else:
            rows.append((_order(old), f"- {_where(old)}, only in the snapshot{_rest(old)}"))
    rows += [(_order(new), f"+ {_where(new)}, only in the build{_rest(new)}") for es in pending.values() for new in es]
    return [line for _, line in sorted(rows)]


def layout_diff(expected: dict, actual: dict, limit: int = MAX_LINES) -> list[str]:
    """How layout `actual` differs from layout `expected`: at most `limit` lines, then a count of the rest; empty
    when they match. Entities, wires and anything else compare as multisets, so their order never matters."""
    lines = []
    for key in sorted(expected.keys() | actual.keys(), key=lambda k: (k != "entities", k != "wires", k)):
        old, new = _items(expected.get(key)), _items(actual.get(key))
        gone, came = _minus(old, new), _minus(new, old)
        if key == "entities":
            lines += _entity_lines(gone, came)
        else:
            what = key.removesuffix("s")
            lines += [f"- {what} only in the snapshot: {_clip(_canon(w))}" for w in gone]
            lines += [f"+ {what} only in the build: {_clip(_canon(w))}" for w in came]
    if len(lines) > limit:
        lines = lines[:limit] + [f"... and {len(lines) - limit} more"]
    return lines


def _line(item) -> str:
    """An item's fixture line: an entity's name and position first, then its other fields by key."""
    if isinstance(item, dict) and {"name", "position"} <= item.keys():
        rest = json.loads(_canon({k: v for k, v in item.items() if k not in ("name", "position")}))
        item = {"name": item["name"], "position": item["position"], **rest}
    return json.dumps(item)


def write_fixture(path: Path, spec: dict, confirmed: str, found: dict) -> None:
    """The fixture as JSON with one entity or wire a line, so a git diff shows exactly what moved."""
    parts = [f'  "spec": {json.dumps(spec)}', f'  "confirmed": {json.dumps(confirmed)}']
    for key, items in found.items():
        body = ",\n".join(f"    {_line(item)}" for item in _items(items))
        parts.append(f"  {json.dumps(key)}: [\n{body}\n  ]" if body else f"  {json.dumps(key)}: []")
    path.write_text("{\n" + ",\n".join(parts) + "\n}\n")


def _load(path: Path) -> tuple[dict, dict]:
    """(the fixture, its layout)."""
    fixture = json.loads(path.read_text())
    assert set(OWN) <= fixture.keys() and "entities" in fixture, f"{path.name} needs spec, confirmed and entities"
    return fixture, {k: v for k, v in fixture.items() if k not in OWN}


# --- the snapshots ----------------------------------------------------------------------------------------------

def test_there_are_snapshots():
    assert FILES, f"no snapshots in {FIXTURES}"


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_a_confirmed_layout_is_unchanged(path):
    fixture, expected = _load(path)
    found = layout(build(fixture["spec"]).blueprint)
    if os.environ.get(UPDATE, "") not in ("", "0"):
        write_fixture(path, fixture["spec"], fixture["confirmed"], found)
        return
    diff = layout_diff(expected, found)
    if diff:
        pytest.fail(f"{path.name} ({fixture['confirmed']}):\n" + "\n".join(diff) + f"\n{HINT}", pytrace=False)


# --- the comparison catches what it must, and only that -----------------------------------------------------------
# Each builds a fixture's spec and perturbs one thing after the build. It compares against that same spec's
# unperturbed build rather than the fixture, so a stale fixture fails only its snapshot test above.

NORTH = FIXTURES / "circuit_block_north.json"  # small, and no wires: a single substation
IRON = FIXTURES / "smelting_column_iron.json"  # a pole ladder's wires


def _built(path: Path) -> tuple[object, dict]:
    """(the fixture's blueprint, freshly built, and its layout before any perturbation)."""
    fixture, _ = _load(path)
    bp = build(fixture["spec"]).blueprint
    return bp, layout(bp)


def _at(e) -> tuple[float, float]:
    return e.position.x, e.position.y


def test_a_moved_label_is_reported():
    bp, before = _built(NORTH)
    panel = next(e for e in bp.entities if e.name == LABEL)
    (x, y), icon = _at(panel), _canon({"icon": {"name": panel.icon.name, "type": "item"}})
    panel.tile_position = (panel.tile_position.x - 1, panel.tile_position.y)
    assert layout_diff(before, layout(bp)) == [
        f"+ {LABEL} at ({x - 1:g}, {y:g}), only in the build: {icon}",
        f"- {LABEL} at ({x:g}, {y:g}), only in the snapshot: {icon}",
    ]


def test_a_turned_belt_is_reported():
    bp, before = _built(NORTH)
    belt = next(e for e in bp.entities if e.name == "turbo-transport-belt" and e.direction == Direction.EAST)
    belt.direction = Direction.WEST
    x, y = _at(belt)
    assert layout_diff(before, layout(bp)) == [f"~ turbo-transport-belt at ({x:g}, {y:g}): direction 4 -> 12"]


def test_a_missing_wire_is_reported():
    bp, before = _built(IRON)
    a, b = before["wires"][0]
    at = {(e.name, *_at(e)): e for e in bp.entities}
    bp.remove_power_connection(at[tuple(a[:3])], at[tuple(b[:3])])
    assert layout_diff(before, layout(bp)) == [f"- wire only in the snapshot: {_canon([a, b])}"]


def test_a_long_diff_is_capped():
    _, before = _built(IRON)
    diff = layout_diff(before, {"entities": [], "wires": []})
    removed = len(before["entities"]) + len(before["wires"])
    assert len(diff) == MAX_LINES + 1 and diff[-1] == f"... and {removed - MAX_LINES} more"


def test_the_creation_order_doesnt_matter(monkeypatch):
    """The snapshot doesn't depend on entity numbers: a generator listing its entities backwards, which numbers
    them backwards, gives the same layout, wires included."""
    fixture, _ = _load(IRON)
    forwards = layout(build(fixture["spec"]).blueprint)
    orig = generators.REGISTRY[fixture["spec"]["type"]]

    def backwards(spec):
        entities, notes, ports = orig(spec)
        return entities[::-1], notes, ports

    monkeypatch.setitem(generators.REGISTRY, fixture["spec"]["type"], backwards)
    found = layout(build(fixture["spec"]).blueprint)
    assert found["wires"] and layout_diff(forwards, found) == []
