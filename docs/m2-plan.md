# M2 plan: solver and stacked green circuits

Milestone 2 of the v2 optimizer (`PROJECT_BRIEF.md`, v2 section). Researched 2026-10-11. **Status (2026-10-11):** pieces A, C and D are done on branch `v2-m2-acd` (see "Progress" below). Next: B, then E, then F. Target: "fill a turbo belt of green circuits" becomes a blueprint that passes the harness.
- **Input:** iron and copper plates on belts. The block makes its own copper cable.
- **Output:** 240/s on a stacked turbo belt.
- **Defaults:** everything researched; legendary electromagnetic plants, legendary productivity-3 in the machines, legendary beacons with legendary speed-3.

## Research findings

Sources: local 2.0.77 data (`data/`, `doc-html/`), a draftsman 3.3.1 probe, and the wiki and forums. The probe's scripts are in the session scratchpad.

**Game data (2.0.77)**

*Machines and recipes*
- Electromagnetic plant: 4×4, crafting speed 2, base productivity +50%, 5 module slots, 2 MW.
- Copper cable and electronic circuit are both in its "electronics" category, and both take 0.5 s.
- No research adds productivity to either recipe. The cap is +300%.

*Quality*
- Levels are 0/1/2/3/5. A level multiplies by 1 + 0.3·level, so legendary is ×2.5.
- That multiplier applies to crafting speed, inserter speed and module bonuses, but not to module penalties.
- Belts and loaders have no quality.

*Modules and beacons*
- Legendary speed-3 gives +125% speed and +70% consumption.
- Legendary productivity-3 gives +25% productivity, −15% speed and +80% consumption.
- Beacons: 3×3, reach 3, 2 slots. Distribution effectivity is 1.5 + 0.2·level (legendary 2.5). The profile is ≈1/√(number of beacons).
- **2.0 rounds effects to whole percents**, which staff say is fixed in 2.1. The solver has to match 2.0.77, so it is calibrated against the harness.

*Machine throughput*
- A machine can finish **more than one craft per tick** (since 2.0.7).
- One legendary plant with 5 legendary prod-3 and N legendary beacons:

  | N | Crafting speed | Productivity | Circuits/s if making circuits |
  |---|---|---|---|
  | 1 | 32.5 | +175% | 179 |
  | 2 | 45.45 | +175% | 250 |
  | 4 | 63.8 | +175% | 351 |

- **240/s needs 87.3 circuit crafts/s.** That consumes 87.3 iron/s and 262 cable/s; the cable takes 47.6 cable crafts/s, which consume 47.6 copper/s.

*Inserters, research and belts*
- Stack inserter: hand 1 + 4 + 11 research = 16, and it puts up to 4 items per belt slot. Legendary is about 120/s chest-to-chest and about 80/s chest-to-turbo-belt (wiki data).
- **No belt-to-machine figure for stacked belts is published.** We measure it.
- A turbo belt carries 60/s, or **240/s stacked** (120/s per lane). The turbo underground spans 11.
- **The turbo loader is hidden** (it can't be built in survival) and can't output stacked items.

*Power*
- Substation: 18×18, reach 18. Legendary is 28×28, reach 28.
- Each maxed plant draws tens of MW.

**draftsman 3.3.1**
- It expresses everything needed: plants, beacons, entity, recipe and module quality, stack inserters, turbo belts and substations.
- Everything round-trips, and a full M2-like build raises no false warnings.
- *Gaps we must cover ourselves:*
  - It doesn't check modules: productivity in a beacon, or too many modules, both pass.
  - It doesn't check underground pairing or distance.
  - It has no beacon-reach helper.
  - `generate_power_connections(only_axis=True)` never wires a 2×2 pole to a 1×1 pole.
  - It ignores quality's effect on pole reach.

**The consequence:** the block isn't limited by machines. **It is limited by inserters and belts.**
- About 3 cable inserters move 262/s between plants.
- About 2 iron inserters pull from a stacked belt.
- About 4 output inserters fill both 120/s lanes, because an inserter drops onto the far lane only (F1).
- That all has to fit around a 4×4 plant together with its beacons.

## Decided: the machine bar (user, 2026-10-11)

Beacons come in whole steps, so one machine can't be sized exactly to the target.
- A cable plant with 1 beacon is about 73% busy.
- The circuit plant with 2 beacons is about 96% busy, which only just passes.

The bar treats an over-capacity machine that's idle ("no ingredients") like a starved one, so honest beaconed designs fail. **Decided (piece A implements it):**
- Fail a machine only if it is **blocked on output** for more than 5% of the window (`full_output`), or if its output buffer grows.
- The output-rate bar (98%) still catches an input bottleneck.
- Report each machine's utilisation instead of judging it.

## Work breakdown

The pieces run in parallel where possible:

| Piece | Files | Delivers | Depends on |
|---|---|---|---|
| **A. Harness for M2** | `harness/mod/control.lua`, `runner.py`, `verdict.py` | Stacked input feeding: each tick, the script inserts stacks of 4 at the back of each input port's belt (`insert_at_back(items, 4)`). The port contract gains `stack` (1–4). Research-all runs; the verdict change above. | — |
| **B. Measured primitives** | `tests/test_harness_primitives.py`, techniques entries | Micro-blueprints run in the harness. Legendary stack inserter rates for stacked belt→plant, plant→plant and plant→stacked belt (per lane). The real crafting speed of a plant with N beacons, which checks the solver and the 2.0 rounding. | A (stacked feed) |
| **C. Solver** | `src/blueprint_smith/effects.py` (+ `ratios.py`), `tests/test_effects.py` | Quality, module, beacon and research maths: speed, productivity (capped), consumption, items/s per machine; inserter rates taken from B's measurements. Unit-tested against the numbers above. | — (B checks it) |
| **D. Checks** | `checks.py`, `tests/test_checks_m2.py` | Module validity (allowed effects, slot count), beacon reach (which machines each beacon affects, matched to the solver), underground pairing and distance, hidden entities rejected. Each check gets a mutation test. | — |
| **E. Generator** | `generators/circuit_block.py` (+ shared helpers) | A parametric layout: circuit and cable plants with direct insertion, beacons, inserter counts per link, a stacked iron input, a copper input, and a stacked output filling both lanes. The parameters are what the optimiser varies. | C, D; B's rates to set ranges |
| **F. Optimiser** | `src/blueprint_smith/optimise.py`, CLI `optimise` | Enumerate variants, prefilter them with the solver, run the harness on survivors in parallel, and return the smallest passing footprint (ties broken by power). | A, E |

A, C and D start now in parallel. B follows A. E follows C and D. F is last.

## Progress

**A, C and D, 2026-10-11** (built in parallel; 375 tests pass, 1 strict xfail):
- **A (harness):**
  - `Port.stack` (1–4) is validated in the pipeline and the mod.
  - Stacked inputs are fed by script (F17): a turbo belt delivers 240.00/s, 120/120 per lane.
  - The loader sink keeps up at 240/s, so `stack` on an output port is informational.
  - The machine bar is implemented: blocked on output for more than 5% fails, and idle time is reported as utilisation (P2). Unpowered time isn't judged, because power is never short in the user's save (user, 2026-10-12).
  - Results now carry each machine's quality, crafting speed and productivity, plus the research bonuses.
- **C (solver):**
  - `effects.py` covers quality, modules, beacons, research, power and demand.
  - The 2.0 whole-percent rounding was fitted on the headless server (F19). That's why the N=2 row reads 45.45: unrounded maths gives 45.44.
  - Nothing boosts circuit or cable productivity. `ratios.py` is unchanged.
- **D (checks):** `module_validity`, `beacon_reach`, `underground_pairing` and `hidden_entities` now run on every blueprint (F24–F27).
  - `checks.beacon_targets(bp)` returns `{machine: [beacons]}`, and that output goes straight into `effects.entity_rates(machine, beacons=...)` (`tests/test_m2_integration.py`).
- **For B:**
  - `products_finished` counts items including the productivity bonus (F18).
  - M2 runs must pass `research="all"`, because the stacked feed works without research.

## Verification plan

1. **Baseline:** `.venv/bin/pytest -q` is green (187 passed, 1 xfail).
2. **A:**
   - A plain stacked turbo belt fed by the script delivers 240/s, 120/120 per lane.
   - The M1 calibration suite still passes, since research stays `none` for M1 cases.
   - The verdict tests cover blocked versus idle.
3. **B:** each measured rate is repeatable across 2 runs within 2%, and is recorded in `docs/techniques.md` as "Headless 2.0.77".
4. **C:**
   - Unit tests match the table above.
   - The solver's speed for N = 1, 2 and 4 beacons matches B's harness measurement within 1%, which also tests the 2.0 rounding.
5. **D:** each check catches its mutation (a productivity module in a beacon, 6 modules in a plant, a beacon out of reach, an unpaired underground, a turbo loader).
6. **E:**
   - Static tests: ports, flow and checks.
   - Harness: the default variant delivers at least 98% of 240/s, both lanes about 120/s, and nothing blocked.
7. **F:**
   - `blueprint-smith optimise` on the green-circuit request returns a passing blueprint.
   - It rejects a variant the harness fails, such as too few output inserters.
   - It picks the smallest passing footprint.
8. **Human:** the user imports the chosen blueprint in-game and confirms 240/s (the brief's spot-check).
