# M2 plan: solver and stacked green circuits

Milestone 2 of the v2 optimizer (`PROJECT_BRIEF.md`, v2 section). Researched 2026-10-11. **Status (2026-10-12):**
- A, C and D are done (PR #2, branch `v2-m2-acd`).
- B is done (PR #3, branch `v2-m2-b`).
- E is done (PR #4, branch `v2-m2-e`), and its default block is confirmed in-game (2026-10-12).
- F is built (branch `v2-m2-f`): `blueprint-smith optimise` turns "fill a turbo belt of green circuits" into an 11×11 blueprint that passes the harness. **The user's in-game spot-check passed on 2026-10-12, so M2 is done.**
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
- **No belt-to-machine figure for stacked belts is published.** We measured it (piece B, F28): 87.47/s for a legendary stack inserter.
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
- 3 cable inserters move 262/s between plants (120/s each, measured).
- 2 iron inserters pull 87.3/s from a stacked belt. One manages 87.47/s, which leaves only 0.2% to spare.
- 1 copper inserter covers 47.6/s.
- 4 output inserters fill both 120/s lanes, 2 per lane on opposite sides of the belt. An inserter drops onto the far lane only (F1): the first adds 80/s and the second the remaining 40/s.
- That all has to fit around a 4×4 plant together with its beacons.

## Decided: the machine bar (user, 2026-10-11)

Beacons come in whole steps, so one machine can't be sized exactly to the target.
- A cable plant with 1 beacon is about 73% busy.
- The circuit plant with 2 beacons is about 96% busy, which only just passes.

The bar treats an over-capacity machine that's idle ("no ingredients") like a starved one, so honest beaconed designs fail. **Decided (piece A implements it):**
- Fail a machine only if it is **blocked on output** for more than 5% of the window (`full_output`), or if its output buffer grows.
- The output-rate bar (98%) still catches an input bottleneck.
- Report each machine's utilisation instead of judging it.

**Amended (user, 2026-10-12):**
- Unpowered time isn't judged.
- A machine that unloads only into other machines isn't judged on blocking, nor (follow-up to F) on output growth. Under direct insertion, the circuit block's cable plant read 55% blocked while the block delivered 240/s: spare capacity there shows as blocked, not idle.

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
  - M2 runs must pass `research="all"`, because the stacked feed works without research.

**B, 2026-10-12** (394 tests pass, 1 strict xfail):
- **Harness additions:**
  - Every inserter's items moved are counted from its hand.
  - Measurement-only `probes` script-feed or drain chosen machines, so the link under test is the only bottleneck.
- **Measured** (F28; stored in `effects.LEGENDARY_STACK_INSERTER` and held there by `tests/test_harness_primitives.py`). These are legendary stack inserters with everything researched:

  | Link | Rate |
  |---|---|
  | Full stacked belt → plant | 87.47/s (the same for iron into circuits and copper into cable) |
  | Plant → plant | 120/s |
  | Plant → empty stacked lane | 80/s, far lane only. A 2nd inserter on that lane adds 40/s, up to its 120/s cap. |

  Every rate repeats exactly across 2 runs.
- **Solver check:** a plant with 1, 2 or 4 beacons runs at 32.5, 45.45 and 63.75 crafting speed. The solver gives the same, to 1e-6 (so the 2.0 rounding is tested), and output matches within 0.01%.
- **Correction (F18):** `products_finished` counts crafts, productivity's bonus crafts included, not items. The harness was already right to multiply by product amount, and the multi-product open question is closed.

**E, 2026-10-12** (432 tests pass, 1 strict xfail):
- **`circuit_block`:** the layout you approved, drawn in `generators/circuit_block.py`, is 13×11 tiles.
  - A legendary cable plant hands cable to a legendary circuit plant by direct insertion, and 2 shared beacons reach both.
  - Copper and iron come in stacked from the west; circuits leave south on a stacked turbo belt.
  - The second lane is filled by a side-load stub (T5).
- **Spec options:** `rate` (up to 240), `quality`, `beacons` (0–2), and `iron_inserters`, `cable_inserters`, `east_inserters` and `north_inserters` (1–4 each). Defaults come from the solver and F28's rates, sized to the 98% bar. Under-sized parts become `WARNING:` notes.
- **Harness:** the default passes with research on: 239.71/s crafted (99.9%), lanes 120.00/120.00, and the circuit plant blocked 1.8%. One stub inserter gives lanes 120/80 and fails.
- **In-game, 2026-10-12:** the default block ran in the user's game with both output lanes full and the stub side-loading as designed. The user: "It works perfectly." That's the harness's first in-game agreement on a non-furnace blueprint.
- **Machine bar:** a machine that unloads only into other machines is no longer judged on blocking (see the amendment above).
- **For F:**
  - Every link's inserter count is an option, so variants are cheap to enumerate.
  - The footprint is fixed at 13×11 except through the beacon count.
  - Builds need `research="all"`; the notes say so.

**F, 2026-10-12** (527 tests pass, 1 strict xfail). The user chose to build the optimiser and a second layout together, by two sub-agents in parallel:
- **Registry contract:** `register(..., variants=, research=)`. `VARIANTS[type](request)` yields candidate specs that the solver says could pass, and `RESEARCH[type]` is the research the harness needs. `evaluate` and `build --evaluate` now default `--research` to it, so `circuit_block` no longer needs `--research all` by hand.
- **Second layout, `copper: "north"` (T6):** approved by the user. Copper comes down into the cable plant from beside the substation, so the block is 11×11 (121 tiles) instead of 13×11 (143). At 240/s the machines and beacons can't shrink, so input routing is the only footprint lever. Harness: 239.74/s crafted, lanes 120/120.
- **`circuit_block.sizing`** holds the link math the notes and `variants` share. Its `bound` is the block's maximum output with no margin. `variants` keeps every copper side, beacon count and inserter count whose bound reaches 98% of the rate: 144 at 240/s.
- **`optimise.py` and `blueprint-smith optimise REQUEST`:**
  1. Builds every variant serially.
  2. Ranks by footprint, then by a power estimate (`power_estimate`: machines and beacons from `effects.py`, plus an upper bound per inserter). The harness doesn't measure power draw.
  3. Runs the harness best-first in parallel batches and stops at the first batch with a pass.
- **The real run** (`{"item": "electronic-circuit", "rate": 240}`) took 17 s and 8 harness runs. It chose the north layout with 2 beacons and iron 1, cable 3, east 2, north 2 inserters: 240.01/s, lanes 120/120.
  - **One iron inserter** carries 87.47/s against 87.27/s needed. The static 98% margin warns about it, but the harness passes it.
  - **Two of the 8 failed** on the cable plant's output growing (44 and 24 items over the window), although it feeds only machines. That's the `GROWTH_MAX` follow-up from the PR #4 review showing up, and it doesn't change the winner. The same two fail on every run. *Fixed in the follow-up: the user exempted machine-only feeders from growth, and all 8 runs then pass.*
- **In-game, 2026-10-12:** the user ran the optimiser's pick: "It worked well". Their screenshot shows both lanes full, with the single iron inserter keeping up.
- **The user's tweak (T5):** they moved the 2 stub inserters to the east end of the plant's top edge and started the stub under the first one, which saves 2 turbo belts. The generator now builds the stub that way for both layouts, and `check_flow` rejects stub belt west of the first stub inserter, or a gap in the stub. Harness lanes stay at 120/120, and the optimiser's pick is unchanged.

## Verification plan

1. **Baseline:** `.venv/bin/pytest -q` is green (187 passed, 1 xfail).
2. **A:**
   - A plain stacked turbo belt fed by the script delivers 240/s, 120/120 per lane.
   - The M1 calibration suite still passes, since research stays `none` for M1 cases.
   - The verdict tests cover blocked versus idle.
3. **B:** each measured rate is repeatable across 2 runs within 2%, and is recorded in `docs/techniques.md` as "Headless 2.0.77". *Done 2026-10-12: identical across runs (F28).*
4. **C:**
   - Unit tests match the table above.
   - The solver's speed for N = 1, 2 and 4 beacons matches B's harness measurement within 1%, which also tests the 2.0 rounding. *Done 2026-10-12: speed is held to 1e-6, because 1% can't see the rounding (45.45 versus 45.44 is 0.014%).*
5. **D:** each check catches its mutation (a productivity module in a beacon, 6 modules in a plant, a beacon out of reach, an unpaired underground, a turbo loader).
6. **E:**
   - Static tests: ports, flow and checks.
   - Harness: the default variant delivers at least 98% of 240/s, both lanes about 120/s, and nothing blocked. *Done 2026-10-12: 99.9%, lanes 120/120, the circuit plant blocked 1.8% (`tests/test_circuit_block.py`).*
7. **F:** *Done 2026-10-12 (see Progress).*
   - `blueprint-smith optimise` on the green-circuit request returns a passing blueprint.
   - It rejects a variant the harness fails, such as too few output inserters.
   - It picks the smallest passing footprint.
8. **Human:** the user imports the chosen blueprint in-game and confirms 240/s (the brief's spot-check). *Done 2026-10-12: "It worked well".*
