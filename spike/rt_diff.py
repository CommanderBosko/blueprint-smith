import json, warnings
from draftsman.blueprintable import Blueprint
from draftsman.constants import Direction
from draftsman.entity import AssemblingMachine, TransportBelt
from draftsman.utils import string_to_JSON

bp = Blueprint()
bp.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(0, 0), recipe="electronic-circuit"))
bp.entities.append(TransportBelt("transport-belt", tile_position=(4, 0), direction=Direction.EAST))
s1 = bp.to_string()
j1 = string_to_JSON(s1)
s2 = Blueprint.from_string(s1).to_string()
j2 = string_to_JSON(s2)
print("no-label identical JSON:", j1 == j2, "| string identical:", s1 == s2)
if j1 != j2:
    print(json.dumps(j1, sort_keys=True)); print(json.dumps(j2, sort_keys=True))

bp.label = "spike"
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    bp.to_string()
    print("label warnings:", [str(x.message) for x in w])

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    b = Blueprint()
    b.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(0, 0)))
    b.entities.append(AssemblingMachine("assembling-machine-3", tile_position=(1, 1)))
    print("overlap warning full text:", [(type(x.message).__name__, str(x.message)) for x in w])
