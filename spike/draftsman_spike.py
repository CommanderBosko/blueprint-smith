"""Throwaway spike: does draftsman 3.x work against the installed 2.0.77 + Space Age data?"""
import json
import warnings

from draftsman import __version__
from draftsman.blueprintable import Blueprint
from draftsman.constants import Direction
from draftsman.data import entities, recipes
from draftsman.entity import (
    AssemblingMachine,
    TransportBelt,
    UndergroundBelt,
)
from draftsman.utils import string_to_JSON

print("draftsman", __version__)

# 1. Direction numeric values
print("directions:", {d.name: int(d) for d in Direction if d.name in ("NORTH", "EAST", "SOUTH", "WEST", "NORTHEAST")})

# 2. Footprints / underground range from real prototype data
for name in ("assembling-machine-3", "splitter", "electric-furnace", "foundry", "biochamber", "big-electric-pole"):
    try:
        e = entities.raw[name]
        print(name, "collision_box", e.get("collision_box"), "tile", e.get("tile_width"), e.get("tile_height"))
    except KeyError:
        print(name, "MISSING")
for name in ("underground-belt", "fast-underground-belt", "express-underground-belt"):
    print(name, "max_distance", entities.raw[name]["max_distance"])
print("recipe electronic-circuit:", recipes.raw["electronic-circuit"].get("ingredients"), recipes.raw["electronic-circuit"].get("energy_required"))
print("assembling-machine-3 crafting_speed:", entities.raw["assembling-machine-3"]["crafting_speed"])

# 3. Build a small blueprint and round-trip it
bp = Blueprint()
bp.label = "spike"
bp.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(0, 0), recipe="electronic-circuit", direction=Direction.NORTH))
for x in range(4, 8):
    bp.entities.append(TransportBelt("transport-belt", tile_position=(x, 0), direction=Direction.EAST))
bp.entities.append(UndergroundBelt("underground-belt", tile_position=(8, 0), direction=Direction.EAST, io_type="input"))
bp.entities.append(UndergroundBelt("underground-belt", tile_position=(12, 0), direction=Direction.EAST, io_type="output"))

s1 = bp.to_string()
j1 = string_to_JSON(s1)
bp2 = Blueprint.from_string(s1)
s2 = bp2.to_string()
print("round-trip string identical:", s1 == s2)
print("round-trip JSON identical:", string_to_JSON(s1) == string_to_JSON(s2))
print("version field:", j1["blueprint"].get("version"))
print("entity sample:", json.dumps(j1["blueprint"]["entities"][0]))
print("underground sample:", json.dumps(j1["blueprint"]["entities"][-2]))

# 4. Validation: does it catch an overlap and a bad name?
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    bad = Blueprint()
    bad.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(0, 0)))
    try:
        bad.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(1, 1)))
        print("overlap: accepted without error;", len(w), "warnings:", [str(x.message)[:80] for x in w])
    except Exception as ex:
        print("overlap: raised", type(ex).__name__, str(ex)[:120])
try:
    Blueprint().entities.append(TransportBelt("not-a-real-belt"))
    print("bad name: accepted")
except Exception as ex:
    print("bad name: raised", type(ex).__name__)
