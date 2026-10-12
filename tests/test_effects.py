import re
from pathlib import Path

import pytest
from draftsman.entity import new_entity

from blueprint_smith import effects, ratios
from blueprint_smith.effects import Beacon, Module
from blueprint_smith.errors import SpecError

L = "legendary"
EM = "electromagnetic-plant"
PROD3 = [Module("productivity-module-3", L)] * 5
SPEED_BEACON = Beacon([Module("speed-module-3", L)] * 2, L)


def em_circuits(n_beacons, recipe="electronic-circuit", research="none"):
    return effects.machine_rates(EM, recipe, quality=L, modules=PROD3, beacons=[SPEED_BEACON] * n_beacons, research=research)


# The plan's table. 2.0 rounding: each beacon sends trunc(250% x 2.5) = 625%, the plant gets
# round_half_up(N x 625% x profile[N]) once. N=2: 883.875% -> 884% (unrounded maths gives 45.44375 and 249.94/s).
# LuaEntity.crafting_speed on the 2.0.77 headless server read 32.5, 45.45 and 63.75, and the plants made 178.7,
# 250.0 and 350.6 circuits/s.
@pytest.mark.parametrize("n, speed, per_second", [(1, 32.5, 178.75), (2, 45.45, 249.975), (4, 63.75, 350.625)])
def test_legendary_plant_table(n, speed, per_second):
    r = em_circuits(n)
    assert r.crafting_speed == pytest.approx(speed, abs=1e-9)
    assert r.productivity == pytest.approx(1.75)
    assert r.products == {"electronic-circuit": pytest.approx(per_second, abs=1e-9)}
    assert r.ingredients == {"iron-plate": pytest.approx(per_second / 2.75), "copper-cable": pytest.approx(3 * per_second / 2.75)}


def test_240_circuits_a_second_back_to_plates():
    circuits = em_circuits(2).demand(240)
    assert circuits.crafts_per_second == pytest.approx(87.27, abs=0.01)
    assert circuits.ingredients == {"iron-plate": pytest.approx(87.27, abs=0.01), "copper-cable": pytest.approx(261.8, abs=0.1)}
    cable = em_circuits(1, "copper-cable").demand(circuits.ingredients["copper-cable"])
    assert cable.crafts_per_second == pytest.approx(47.6, abs=0.01)
    assert cable.ingredients == {"copper-plate": pytest.approx(47.6, abs=0.01)}
    assert em_circuits(2).machines_for(240) == 1
    assert em_circuits(1).machines_for(240) == 2


# Effects read with LuaEntity.effects from normal plants on the 2.0.77 headless server (2026-10-11).
S1 = [Module("speed-module-2", "epic"), Module("speed-module", "uncommon")]  # 57% + 26% speed, 60% + 50% consumption
S2 = [Module("speed-module-3", "uncommon")] * 2
S4 = [Module("speed-module-2", "rare")]


@pytest.mark.parametrize("beacon, n, speed, consumption", [
    (Beacon(S1), 1, 1.24, 1.65),  # 83% x 1.5 = 124.5 -> truncated
    (Beacon(S1, "epic"), 1, 1.74, 2.30),  # 110% x float32(2.1) = 230.99998 -> 230
    (Beacon(S4, "epic"), 1, 1.00, 1.25),  # 60% x float32(2.1) -> 125, 48% x 2.1 = 100.8 -> 100
    (Beacon(S2, "epic"), 1, 2.73, 2.94),  # 140% x float32(2.1) rounds to 294.0 in float32
    (Beacon(S1, "rare"), 2, 2.22, 2.96),  # sent 157% / 209%, then 2 x 0.7071 rounded once
    (Beacon(S1), 3, 2.15, 2.86),
    (Beacon(S2, "uncommon"), 2, 3.13, 3.37),
    (Beacon(S2, L), 5, 7.27, 7.83),
    (Beacon([Module("efficiency-module")]), 3, 0.0, -0.78),  # -77.9 rounds half up to -78
    (Beacon([Module("efficiency-module")] * 2), 4, 0.0, -0.80),  # floored
])
def test_beacon_rounding_matches_the_engine(beacon, n, speed, consumption):
    e = effects.machine_effects(EM, beacons=[beacon] * n)
    assert (e.speed, e.consumption, e.productivity) == (pytest.approx(speed), pytest.approx(consumption), pytest.approx(0.5))


def test_mixed_qualities_match_the_engine():
    # A rare plant with 3 epic productivity-2 and 2 rare beacons of S2: crafting speed 13.408 on the server
    r = effects.machine_rates(EM, "electronic-circuit", quality="rare", modules=[("productivity-module-2", "epic")] * 3,
                              beacons=[Beacon(S2, "rare")] * 2)
    assert (r.effects.speed, r.effects.consumption, r.productivity) == (pytest.approx(3.19), pytest.approx(5.56), pytest.approx(0.83))
    assert r.crafting_speed == pytest.approx(13.408)


def test_quality_scales_bonuses_not_penalties():
    assert effects.module_effects(("productivity-module-3", L)) == effects.Effects(
        speed=pytest.approx(-0.15), productivity=pytest.approx(0.25), consumption=pytest.approx(0.8), pollution=pytest.approx(0.1))
    assert effects.module_effects(("speed-module-3", L)) == effects.Effects(
        speed=pytest.approx(1.25), consumption=pytest.approx(0.7), quality=pytest.approx(-0.25))
    assert effects.module_effects(("efficiency-module", L)).consumption == pytest.approx(-0.75)  # a reduction is a bonus
    # each module truncates to whole percent: 4% x 1.9 = 7.6% -> 7%, 25 x 2.5 = 62.5 -> 62 (shown as 6.2% quality)
    assert effects.module_effects(("productivity-module", "epic")).productivity == pytest.approx(0.07)
    assert effects.module_effects(("quality-module-3", L)).quality == pytest.approx(0.62)
    assert effects.machine_effects(EM, modules=[("productivity-module", "epic")] * 5).productivity == pytest.approx(0.85)


def test_quality_multiplies_crafting_speed():
    speeds = [effects.machine_rates(EM, "electronic-circuit", quality=q).crafting_speed for q in ("normal", "uncommon", "rare", "epic", L)]
    assert speeds == pytest.approx([2, 2.6, 3.2, 3.8, 5])


def test_productivity_is_capped_at_300_percent():
    assert em_circuits(4, "processing-unit", research={"processing-unit-productivity": 10}).productivity == pytest.approx(2.75)
    capped = em_circuits(4, "processing-unit", research={"processing-unit-productivity": 20})
    assert capped.productivity == pytest.approx(3.0)
    assert capped.effects.productivity == pytest.approx(1.75)  # the machine's own effects leave research out
    assert capped.products == {"processing-unit": pytest.approx(capped.crafts_per_second * 4)}


def test_power_measured_on_the_server():
    # electric network statistics on the 2.0.77 headless server: plant 17 066.7 kW, legendary beacon 80 kW
    r = em_circuits(1)
    assert r.drain == pytest.approx(2e6 / 30)
    assert r.power == pytest.approx(2e6 * 8.5 + 2e6 / 30)
    assert effects.beacon_power(SPEED_BEACON) == pytest.approx(80e3)
    assert effects.beacon_power({"quality": "rare"}) == pytest.approx(320e3)
    assert effects.machine_rates(EM, "electronic-circuit").power == pytest.approx(2e6 + 2e6 / 30)  # quality doesn't change it


def test_consumption_floor():
    beacons = [Beacon([Module("efficiency-module")] * 2)] * 4  # -180% before the floor
    r = effects.machine_rates(EM, "electronic-circuit", beacons=beacons)
    assert r.effects.consumption == pytest.approx(-0.8)
    assert r.power == pytest.approx(2e6 * 0.2 + 2e6 / 30)  # 466.7 kW on the server


def test_research():
    none, every = effects.research_bonuses("none"), effects.research_bonuses("all")
    assert none == effects.Research()
    assert every.recipe_productivity["steel-plate"] == pytest.approx(0.1)
    assert "electronic-circuit" not in every.recipe_productivity and "copper-cable" not in every.recipe_productivity
    assert (every.belt_stack_size_bonus, every.inserter_stack_size_bonus, every.bulk_inserter_capacity_bonus) == (3, 3, 11)
    assert effects.research_bonuses({"steel-plate-productivity": 5}).recipe_productivity == {
        "steel-plate": pytest.approx(0.5), "casting-steel": pytest.approx(0.5)}
    # F14: steel furnaces made 11 crafts instead of 10 with everything researched
    steel = effects.machine_rates("electric-furnace", "steel-plate", research="all")
    assert steel.products["steel-plate"] == pytest.approx(ratios.crafts_per_second("electric-furnace", "steel-plate") * 1.1)
    assert em_circuits(2, research="all").products == em_circuits(2).products


@pytest.mark.parametrize("machine, recipe", [
    ("electric-furnace", "iron-plate"),
    ("electric-furnace", "steel-plate"),
    ("electric-furnace", "stone-brick"),
    ("stone-furnace", "copper-plate"),
    ("assembling-machine-3", "iron-gear-wheel"),
    (EM, "electronic-circuit"),
    (EM, "copper-cable"),
])
def test_without_effects_matches_ratios_exactly(machine, recipe):
    r = effects.machine_rates(machine, recipe)
    product = recipe if recipe in r.products else next(iter(r.products))
    if machine == EM:  # the plant's base +50% is the only difference
        assert r.productivity == 0.5
        assert r.crafts_per_second * ratios.recipe_info(recipe)["amount"] == ratios.crafts_per_second(machine, recipe)
    else:
        assert r.products[product] == ratios.crafts_per_second(machine, recipe)
        for rate in (0.1, 7.5, 7.6, 30):
            assert r.machines_for(rate) == ratios.machines_for_rate(machine, recipe, rate)
    assert r.ingredients == ratios.ingredients_per_second(machine, recipe)


def test_beacons_from_draftsman_entities():
    beacon = new_entity("beacon", tile_position=(0, 0), quality=L)
    beacon.request_modules("speed-module-3", (0, 1), L)
    plant = new_entity(EM, tile_position=(3, 0), quality=L, recipe="electronic-circuit")
    plant.request_modules("productivity-module-3", range(5), L)
    as_dict = {"name": "beacon", "quality": L, "modules": [{"name": "speed-module-3", "quality": L}] * 2}
    assert effects.modules_of(plant) == PROD3
    assert effects.entity_rates(plant, beacons=[beacon, beacon]) == em_circuits(2)
    assert effects.machine_rates(EM, "electronic-circuit", quality=L, modules=PROD3, beacons=[as_dict] * 2) == em_circuits(2)


def test_unknown_names_raise_spec_errors():
    with pytest.raises(SpecError, match="crafting machine"):
        effects.machine_rates("transport-belt", "electronic-circuit")
    with pytest.raises(SpecError, match="recipe"):
        effects.machine_rates(EM, "no-such-recipe")
    with pytest.raises(SpecError, match="can't craft"):
        effects.machine_rates("electric-furnace", "electronic-circuit")
    with pytest.raises(SpecError, match="module"):
        effects.machine_rates(EM, "electronic-circuit", modules=["speed-module-9"])
    with pytest.raises(SpecError, match="quality"):
        effects.machine_rates(EM, "electronic-circuit", quality="mythic")
    with pytest.raises(SpecError, match="quality"):
        Module("speed-module", "mythic")
    with pytest.raises(SpecError, match="beacon"):
        Beacon(name="substation")
    with pytest.raises(SpecError, match="technology"):
        effects.research_bonuses({"electronic-circuit-productivity": 1})
    with pytest.raises(SpecError, match="level"):
        effects.research_bonuses({"stack-inserter": 2})
    with pytest.raises(SpecError, match="research"):
        effects.research_bonuses("some")


def _lua_data_dir():
    for d in (Path.home() / ".local/share/Steam/steamapps/common/Factorio/data",
              Path.home() / ".cache/blueprint-smith/factorio-headless-2.0.77/factorio/data"):
        if (d / "space-age/prototypes/technology.lua").is_file():
            return d
    pytest.skip("Factorio Lua data isn't installed")


def test_technology_table_matches_the_lua_data():
    kinds = {"change-recipe-productivity": "recipe", "belt-stack-size-bonus": "belt",
             "inserter-stack-size-bonus": "inserter", "bulk-inserter-capacity-bonus": "bulk"}
    found = {}
    for path in ("base/prototypes/technology.lua", "space-age/prototypes/technology.lua"):
        src = (_lua_data_dir() / path).read_text()
        for m in re.finditer(r'type = "([a-z-]+)",\s*(?:recipe = "([^"]+)",\s*)?(?:change|modifier) = ([0-9.]+)', src):
            if m[1] in kinds:
                tech = re.findall(r'\n    name = "([^"]+)"', src[:m.start()])[-1]
                found.setdefault(tech, []).append((kinds[m[1]], m[2], float(m[3])))
    assert {t: sorted(fx, key=str) for t, fx in found.items()} == {
        t: sorted(fx, key=str) for t, fx in effects.TECHNOLOGIES.items()}
