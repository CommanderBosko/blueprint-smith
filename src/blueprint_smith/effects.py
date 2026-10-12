"""Effect-aware machine rates: quality, modules, beacons and research, matched to Factorio 2.0.77.

`machine_rates()` is the entry point. Beacons are passed in as data (the ones whose reach covers the machine);
this module does no geometry. With no modules, normal quality and no research it agrees exactly with `ratios`.
"""
import math
import re
import struct
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from draftsman.data import entities, modules as module_data, qualities, recipes

from . import ratios
from .errors import SpecError

FIELDS = ("speed", "productivity", "consumption", "pollution", "quality")
_GOOD_SIGN = {"speed": 1, "productivity": 1, "quality": 1, "consumption": -1, "pollution": -1}
# Lowest possible sum of each effect, in percent (prototype docs, `Effect`).
_FLOOR = {"speed": -80, "consumption": -80, "pollution": -80, "productivity": 0, "quality": 0}

# --- 2.0 rounding -------------------------------------------------------------------------------------------
# 2.0 keeps every effect as int16 hundredths ("EffectValue: precision is ignored beyond two decimals", prototype
# docs); staff say 2.1 drops this. The three steps below were fitted to LuaEntity.effects read on the 2.0.77
# headless server: 476 values from 119 electromagnetic plants (every beacon quality, 1-6 beacons, mixed module
# qualities), all matched, as did LuaItemPrototype.get_module_effects for every module and quality. Measured
# crafting and power agreed too. Everything here is in percent; set ROUND_2_0 = False for unrounded (2.1-style) maths.
ROUND_2_0 = True


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def _pct(value: float) -> float:
    """A prototype EffectValue in percent ("0.567 results in 0.56")."""
    if not ROUND_2_0:
        return value * 100
    return math.trunc(value * 100 + math.copysign(1e-6, value))


def _module_pct(base_pct: float, multiplier: float) -> float:
    """One module's effect at a quality: the bonus x quality multiplier, truncated to whole percent."""
    return math.trunc(base_pct * multiplier) if ROUND_2_0 else base_pct * multiplier


def _beacon_pct(modules_pct: float, effectivity: float) -> float:
    """What one beacon sends: its modules' summed percent x distribution effectivity, in float32, truncated."""
    return math.trunc(_f32(_f32(modules_pct) * _f32(effectivity))) if ROUND_2_0 else modules_pct * effectivity


def _received_pct(total: float) -> float:
    """What the machine gets: the sum over its beacons of sent x profile[N], rounded half up once."""
    return math.floor(total + 0.5) if ROUND_2_0 else total


# --- research -----------------------------------------------------------------------------------------------
# From data/base/prototypes/technology.lua and data/space-age/prototypes/technology.lua (2.0.77): draftsman 3.3.1
# has no technology data. Each entry is (bonus kind, recipe or None, amount per level). The productivity
# technologies are infinite; "all" researches every technology once, like LuaForce.research_all_technologies()
# (checked on the headless server: steel-plate +10%, belt stack +3, inserter stack +3, bulk capacity +11).
# Nothing boosts electronic-circuit or copper-cable.
_RECIPE, _BELT, _INSERTER, _BULK = "recipe", "belt", "inserter", "bulk"
TECHNOLOGIES: dict[str, tuple[tuple[str, str | None, float], ...]] = {
    "asteroid-productivity": tuple((_RECIPE, r, 0.1) for r in (
        "carbonic-asteroid-crushing", "oxide-asteroid-crushing", "metallic-asteroid-crushing",
        "advanced-carbonic-asteroid-crushing", "advanced-oxide-asteroid-crushing", "advanced-metallic-asteroid-crushing")),
    "processing-unit-productivity": ((_RECIPE, "processing-unit", 0.1),),
    "scrap-recycling-productivity": ((_RECIPE, "scrap-recycling", 0.1),),
    "steel-plate-productivity": ((_RECIPE, "steel-plate", 0.1), (_RECIPE, "casting-steel", 0.1)),
    "low-density-structure-productivity": ((_RECIPE, "low-density-structure", 0.1), (_RECIPE, "casting-low-density-structure", 0.1)),
    "plastic-bar-productivity": ((_RECIPE, "plastic-bar", 0.1), (_RECIPE, "bioplastic", 0.1)),
    "rocket-fuel-productivity": ((_RECIPE, "rocket-fuel", 0.1), (_RECIPE, "rocket-fuel-from-jelly", 0.1), (_RECIPE, "ammonia-rocket-fuel", 0.1)),
    "rocket-part-productivity": ((_RECIPE, "rocket-part", 0.1),),
    "stack-inserter": ((_BELT, None, 1),),
    "transport-belt-capacity-1": ((_BELT, None, 1),),
    "transport-belt-capacity-2": ((_BELT, None, 1), (_INSERTER, None, 1)),
    "inserter-capacity-bonus-2": ((_INSERTER, None, 1), (_BULK, None, 1)),
    "inserter-capacity-bonus-7": ((_INSERTER, None, 1), (_BULK, None, 2)),
    "bulk-inserter": ((_BULK, None, 1),),
    "inserter-capacity-bonus-1": ((_BULK, None, 1),),
    "inserter-capacity-bonus-3": ((_BULK, None, 1),),
    "inserter-capacity-bonus-4": ((_BULK, None, 1),),
    "inserter-capacity-bonus-5": ((_BULK, None, 2),),
    "inserter-capacity-bonus-6": ((_BULK, None, 2),),
}
INFINITE_TECHNOLOGIES = frozenset(t for t, fx in TECHNOLOGIES.items() if fx[0][0] == _RECIPE)


@dataclass(frozen=True)
class Research:
    recipe_productivity: Mapping[str, float] = field(default_factory=dict)  # recipe -> bonus (0.1 = +10%)
    belt_stack_size_bonus: int = 0  # a belt slot holds 1 + this
    inserter_stack_size_bonus: int = 0  # non-bulk inserters
    bulk_inserter_capacity_bonus: int = 0


def research_bonuses(research: str | Mapping[str, int] | Research = "none") -> Research:
    """`"none"`, `"all"` (every technology once), or explicit levels `{technology: level}` (finite ones take 0 or 1)."""
    if isinstance(research, Research):
        return research
    if research == "none":
        levels = {}
    elif research == "all":
        levels = dict.fromkeys(TECHNOLOGIES, 1)
    elif isinstance(research, Mapping):
        levels = dict(research)
    else:
        raise SpecError(f'research must be "none", "all" or {{technology: level}}, got {research!r}')
    recipe: dict[str, float] = {}
    totals = Counter()
    for tech, level in levels.items():
        if tech not in TECHNOLOGIES:
            raise SpecError(f"unknown or irrelevant technology {tech!r}; known: {', '.join(sorted(TECHNOLOGIES))}")
        if not isinstance(level, int) or level < 0 or (level > 1 and tech not in INFINITE_TECHNOLOGIES):
            raise SpecError(f"{tech} can't be at level {level!r}")
        for kind, target, amount in TECHNOLOGIES[tech]:
            if kind == _RECIPE:
                recipe[target] = recipe.get(target, 0) + amount * level
            else:
                totals[kind] += amount * level
    return Research({r: round(v, 10) for r, v in recipe.items() if v}, totals[_BELT], totals[_INSERTER], totals[_BULK])


# --- inputs -------------------------------------------------------------------------------------------------
def _check_quality(quality: str) -> str:
    if quality not in qualities.raw:
        raise SpecError(f"unknown quality {quality!r}; known: {', '.join(q for q in qualities.raw if q != 'quality-unknown')}")
    return quality


def quality_level(quality: str) -> int:
    return qualities.raw[_check_quality(quality)].get("level", 0)


def quality_multiplier(quality: str) -> float:
    """QualityPrototype::default_multiplier: crafting speed and module bonuses (1 + 0.3 x level; legendary 2.5)."""
    q = qualities.raw[_check_quality(quality)]
    return q.get("default_multiplier", 1 + 0.3 * q.get("level", 0))


@dataclass(frozen=True)
class Module:
    name: str
    quality: str = "normal"

    def __post_init__(self):
        if self.name not in module_data.raw:
            raise SpecError(f"unknown module {self.name!r}")
        _check_quality(self.quality)


@dataclass(frozen=True)
class Beacon:
    """A beacon affecting the machine. `modules` accepts what `machine_rates(modules=...)` does."""
    modules: tuple = ()
    quality: str = "normal"
    name: str = "beacon"

    def __post_init__(self):
        if entities.raw.get(self.name, {}).get("type") != "beacon":
            raise SpecError(f"unknown beacon {self.name!r}")
        _check_quality(self.quality)
        object.__setattr__(self, "modules", tuple(_module(m) for m in self.modules))


def _module(m) -> Module:
    if isinstance(m, Module):
        return m
    if isinstance(m, str):
        return Module(m)
    if isinstance(m, Mapping):
        return Module(m.get("name"), m.get("quality", "normal"))
    if isinstance(m, tuple) and len(m) == 2:
        return Module(*m)
    raise SpecError(f"can't read a module from {m!r}")


def modules_of(entity) -> list[Module]:
    """The modules a draftsman entity requests (its `item_requests`), one `Module` per module item."""
    out = []
    for plan in getattr(entity, "item_requests", None) or ():
        name, quality = plan.id.name, plan.id.quality or "normal"
        if name in module_data.raw:
            slots = getattr(plan.items, "in_inventory", None) or ()
            out += [Module(name, quality)] * sum(p.count for p in slots)
    return out


def _beacon(b) -> Beacon:
    if isinstance(b, Beacon):
        return b
    if isinstance(b, Mapping):
        return Beacon(tuple(b.get("modules", ())), b.get("quality", "normal"), b.get("name", "beacon"))
    if hasattr(b, "item_requests") and hasattr(b, "name"):
        return Beacon(tuple(modules_of(b)), getattr(b, "quality", None) or "normal", b.name)
    raise SpecError(f"can't read a beacon from {b!r}")


# --- effects ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Effects:
    """Effect sums as fractions (0.25 = +25%). `quality` is the raw value, before QualityPrototype::next_probability."""
    speed: float = 0.0
    productivity: float = 0.0
    consumption: float = 0.0
    pollution: float = 0.0
    quality: float = 0.0


def _as_effects(pct: Mapping[str, float]) -> Effects:
    return Effects(**{f: pct.get(f, 0) / 100 for f in FIELDS})


def _module_effect_pct(m: Module) -> dict[str, float]:
    mult = quality_multiplier(m.quality)
    out = {}
    for f, v in (module_data.raw[m.name].get("effect") or {}).items():
        out[f] = _module_pct(_pct(v), mult if v * _GOOD_SIGN[f] > 0 else 1)  # bonuses scale, penalties don't
    return out


def module_effects(module) -> Effects:
    """One module at its quality, like LuaItemPrototype::get_module_effects."""
    return _as_effects(_module_effect_pct(_module(module)))


def _crafter(machine: str) -> dict:
    proto = entities.raw.get(machine) if isinstance(machine, str) else None
    if proto is None or "crafting_speed" not in proto:
        raise SpecError(f"unknown crafting machine {machine!r}")
    return proto


def _effect_pct(proto: dict, modules: Iterable, beacons: Iterable) -> dict[str, float]:
    receiver = proto.get("effect_receiver") or {}
    total = Counter({f: _pct(v) for f, v in (receiver.get("base_effect") or {}).items()})
    modules, beacons = [_module(m) for m in modules], [_beacon(b) for b in beacons]
    if receiver.get("uses_module_effects", True):
        for m in modules:
            total.update(_module_effect_pct(m))
    if receiver.get("uses_beacon_effects", True) and beacons:
        same_type = Counter(b.name for b in beacons)
        sent = Counter()
        for b in beacons:
            bp = entities.raw[b.name]
            n = same_type[b.name] if bp.get("beacon_counter", "total") == "same_type" else len(beacons)
            profile = bp.get("profile") or [1]
            effectivity = bp.get("distribution_effectivity", 1) + bp.get("distribution_effectivity_bonus_per_quality_level", 0) * quality_level(b.quality)
            carried = Counter()
            for m in b.modules:
                carried.update(_module_effect_pct(m))
            for f, v in carried.items():
                sent[f] += _beacon_pct(v, effectivity) * profile[min(n, len(profile)) - 1]
        total.update({f: _received_pct(v) for f, v in sent.items()})
    return {f: max(total.get(f, 0), _FLOOR[f]) for f in FIELDS}


def machine_effects(machine: str, *, modules: Iterable = (), beacons: Iterable = ()) -> Effects:
    """The effects a machine shows (LuaEntity::effects): its base effect, modules and beacons, floored; no research.

    `beacons` are the beacons whose reach covers the machine, each a `Beacon`, a mapping
    `{"name", "quality", "modules"}` or a draftsman beacon entity. Their count picks the beacon profile entry.
    """
    return _as_effects(_effect_pct(_crafter(machine), modules, beacons))


# --- rates --------------------------------------------------------------------------------------------------
_UNITS = {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


def _watts(energy: str) -> float:
    m = re.fullmatch(r"\s*([0-9.eE+-]+)\s*([kMGT]?)W\s*", str(energy))
    if not m:
        raise SpecError(f"can't read power {energy!r}")
    return float(m[1]) * _UNITS[m[2]]


def _products(recipe: str) -> list[dict]:
    return [p for p in recipes.raw[recipe].get("results") or [] if p.get("type", "item") == "item"]


def _main_product(recipe: str, item: str | None) -> str:
    names = [p["name"] for p in _products(recipe)]
    if item is not None:
        if item not in names:
            raise SpecError(f"{recipe} doesn't make {item!r} (it makes {', '.join(names) or 'no items'})")
        return item
    if recipe in names:
        return recipe
    if len(set(names)) == 1:
        return names[0]
    raise SpecError(f"{recipe} makes {', '.join(names) or 'no items'}; say which item")


def _per_craft(recipe: str, productivity: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in _products(recipe):
        amount = p["amount"] if "amount" in p else (p.get("amount_min", 0) + p.get("amount_max", 0)) / 2
        amount *= p.get("probability", 1)
        extra = max(0, amount - p.get("ignored_by_productivity", 0)) * productivity
        out[p["name"]] = out.get(p["name"], 0) + amount + extra
    return out


@dataclass(frozen=True)
class Demand:
    crafts_per_second: float
    ingredients: dict[str, float]  # item ingredients/s; fluids don't ride belts


def recipe_demand(recipe: str, items_per_second: float, *, productivity: float = 0.0, item: str | None = None) -> Demand:
    """Crafts/s and item ingredients/s to make `items_per_second` of `item` (default: the recipe's main product)."""
    info = ratios.recipe_info(recipe)
    crafts = items_per_second / _per_craft(recipe, productivity)[_main_product(recipe, item)]
    return Demand(crafts, {i["name"]: crafts * i.get("amount", 1) for i in info["ingredients"] if i.get("type", "item") == "item"})


@dataclass(frozen=True)
class MachineRates:
    machine: str
    quality: str
    recipe: str
    effects: Effects  # as the machine shows them (no research)
    productivity: float  # what's applied: effects + research, capped at the recipe's maximum (+300%)
    crafting_speed: float
    crafts_per_second: float
    products: dict[str, float]  # item products/s, productivity included
    ingredients: dict[str, float]  # item ingredients/s
    power: float  # watts while working: energy_usage x (1 + consumption, floored at -80%) + drain
    drain: float  # watts, always drawn

    def demand(self, items_per_second: float, item: str | None = None) -> Demand:
        return recipe_demand(self.recipe, items_per_second, productivity=self.productivity, item=item)

    def machines_for(self, items_per_second: float, item: str | None = None) -> int:
        """Machines needed for `items_per_second` of `item` (default: the main product), like `ratios.machines_for_rate`."""
        return max(1, math.ceil(items_per_second / self.products[_main_product(self.recipe, item)] - 1e-9))


def machine_rates(
    machine: str,
    recipe: str,
    *,
    quality: str = "normal",
    modules: Iterable = (),
    beacons: Iterable = (),
    research: str | Mapping[str, int] | Research = "none",
) -> MachineRates:
    """Rates for one `machine` of `quality` crafting `recipe` with `modules`, the `beacons` reaching it, and `research`.

    Modules are `Module`s, names (normal quality), `(name, quality)` pairs or `{"name", "quality"}` mappings.
    Beacons: see `machine_effects`. Validity (allowed effects, slot counts) is the checks' job, not this one's.
    """
    proto = _crafter(machine)
    info = ratios.recipe_info(recipe)
    categories = proto.get("crafting_categories", [])
    if info["category"] not in categories:
        raise SpecError(
            f"{machine} can't craft {recipe!r} (category {info['category']!r}; it crafts {', '.join(categories)})"
        )
    pct = _effect_pct(proto, modules, beacons)
    bonus = research_bonuses(research).recipe_productivity.get(recipe, 0)
    cap = recipes.raw[recipe].get("maximum_productivity", 3.0) * 100
    productivity = min(pct["productivity"] + _pct(bonus), cap) / 100

    speed_mult = (proto.get("crafting_speed_quality_multiplier") or {}).get(quality) or quality_multiplier(quality)
    crafting_speed = proto["crafting_speed"] * speed_mult * (1 + pct["speed"] / 100)
    crafts = crafting_speed / info["time"]

    usage = _watts(proto["energy_usage"])
    if proto.get("quality_affects_energy_usage"):
        q = qualities.raw[quality]
        usage *= (proto.get("energy_usage_quality_multiplier") or {}).get(quality) or q.get("crafting_machine_energy_usage_multiplier", 1)
    source = proto.get("energy_source") or {}
    drain = 0.0
    if source.get("type") == "electric":
        drain = _watts(source["drain"]) if "drain" in source else usage / 30
    return MachineRates(
        machine=machine,
        quality=quality,
        recipe=recipe,
        effects=_as_effects(pct),
        productivity=productivity,
        crafting_speed=crafting_speed,
        crafts_per_second=crafts,
        products={name: crafts * n for name, n in _per_craft(recipe, productivity).items()},
        ingredients={i["name"]: crafts * i.get("amount", 1) for i in info["ingredients"] if i.get("type", "item") == "item"},
        power=usage * (1 + pct["consumption"] / 100) + drain,
        drain=drain,
    )


def entity_rates(entity, *, beacons: Iterable = (), research: str | Mapping[str, int] | Research = "none") -> MachineRates:
    """`machine_rates` for a draftsman crafting-machine entity: its name, quality, recipe and module requests."""
    if not getattr(entity, "recipe", None):
        raise SpecError(f"{entity.name} has no recipe set")
    return machine_rates(entity.name, entity.recipe, quality=getattr(entity, "quality", None) or "normal",
                         modules=modules_of(entity), beacons=beacons, research=research)


def beacon_power(beacon) -> float:
    """Watts one beacon draws: energy_usage x QualityPrototype::beacon_power_usage_multiplier (legendary 1/6)."""
    b = _beacon(beacon)
    return _watts(entities.raw[b.name]["energy_usage"]) * qualities.raw[b.quality].get("beacon_power_usage_multiplier", 1)


# --- inserters ---------------------------------------------------------------------------------------------
# Items/s one legendary stack inserter moves with everything researched (hand 16, belt stack 4), measured on the
# headless 2.0.77 server (F28; tests/test_harness_primitives.py holds these to the harness). The plan's wiki
# figures had no belt-to-machine number for stacked belts. Onto a belt an inserter drops on the far lane only
# (F1), and a stacked turbo lane carries 120/s, so a second inserter on the same lane adds only the 40/s left.
LEGENDARY_STACK_INSERTER = {
    "belt_to_machine": 87.47,  # from a full stacked turbo belt
    "machine_to_machine": 120.0,
    "machine_to_belt": 80.0,  # onto an empty stacked turbo lane
}
