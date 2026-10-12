"""M2 pieces C and D together: the beacons `checks.beacon_targets` finds for a built plant go straight into
`effects.entity_rates`, and give the plan's numbers (docs/m2-plan.md, research findings)."""
import pytest
from draftsman.entity import new_entity

from blueprint_smith import checks, effects, generators
from blueprint_smith.pipeline import build

L = "legendary"


def _plant():
    e = new_entity("electromagnetic-plant", tile_position=(0, 0), quality=L, recipe="electronic-circuit")
    e.request_modules("productivity-module-3", range(5), quality=L)
    return e


def _beacon(at):
    e = new_entity("beacon", tile_position=at, quality=L)
    e.request_modules("speed-module-3", (0, 1), quality=L)
    return e


@pytest.mark.parametrize("beacon_tiles, speed, circuits", [
    ([(-3, 0)], 32.5, 178.75),
    ([(-3, 0), (4, 0)], 45.45, 249.975),  # 2.0 rounds the beacon effect to whole percents: 45.44375 unrounded
])
def test_beacons_found_by_reach_drive_the_solver(monkeypatch, beacon_tiles, speed, circuits):
    entities = [_plant(), *(_beacon(t) for t in beacon_tiles), new_entity("substation", tile_position=(4, 3))]
    monkeypatch.setitem(generators.REGISTRY, "m2_cell", lambda spec: (entities, [], []))
    bp = build({"type": "m2_cell"}).blueprint
    plant = bp.entities[0]
    beacons = checks.beacon_targets(bp)[plant]
    assert len(beacons) == len(beacon_tiles)

    rates = effects.entity_rates(plant, beacons=beacons, research="all")
    assert rates.crafting_speed == pytest.approx(speed)
    assert rates.productivity == pytest.approx(1.75)
    assert rates.products["electronic-circuit"] == pytest.approx(circuits)
