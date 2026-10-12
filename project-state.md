# Project State

## Current Project State

**2026-10-12 (later): M2 piece F, the optimiser, is built on branch `v2-m2-f`. `blueprint-smith optimise` turns "fill a turbo belt of green circuits" into an 11×11 blueprint that passes the harness, and it worked in the user's game. That completes M2's definition of done; merging F is what's left.**
- **In-game spot-check (2026-10-12):** "It worked well." The user's screenshot shows both output lanes full, the north copper inserter feeding the cable plant, and the single iron inserter keeping up.
- **The user's tweak, now in the generator (T5):** the stub inserters sit at the east end of the plant's top edge, and the stub starts under the first one. That's 3 belt tiles instead of 5. `check_flow` enforces it, with mutation tests.
- **Scope (user):** the optimiser and a second layout, built together by two sub-agents in parallel.
- **Second layout (user approved): `circuit_block` with `copper: "north"` (T6).** Copper comes down into the cable plant from beside the substation, which takes the block from 13×11 (143 tiles) to 11×11 (121). At 240/s the machines and beacons can't shrink, so input routing is the only footprint lever. Harness: 239.74/s crafted, lanes 120/120. West stays the default.
- **Registry:** `register(..., variants=, research=)`. `circuit_block` declares `research="all"`, and `evaluate`/`build --evaluate` now default to it.
- **`optimise.py`:** builds every variant, ranks by footprint then estimated power, and runs the harness best-first in parallel batches. The real run took 17 s and 8 harness runs, and chose north with iron 1, cable 3, east 2 and north 2 inserters: 240.01/s, lanes 120/120. It's saved in the session scratchpad and is handed over via `/ingame-test`.
- **Tests:** 535 pass and 1 is a strict xfail (`.venv/bin/pytest -q`, about 85 s).

**2026-10-12: M2 pieces A–E are merged to `main`. The green circuit block makes 240/s in the harness and in-game. Only F, the optimiser, is left.**
- **Merged** in order with merge commits: #2 (pieces A, C and D, plus dropping the unpowered bar), #3 (piece B), #4 (piece E and its in-game confirmation). Each PR's head passed the full suite first, and a code review of each found no blockers (follow-ups under Known Issues). The stack branches are deleted.
- **Tests:** 432 pass and 1 is a strict xfail (`.venv/bin/pytest -q`, about 70 s).
- **`circuit_block` (E):** the layout the user approved is 13×11 tiles and drawn in `generators/circuit_block.py`.
  - A legendary cable plant hands cable to a legendary circuit plant by direct insertion, and 2 shared beacons reach both.
  - Copper and iron come in stacked from the west; circuits leave south on a stacked turbo belt.
  - A side-load stub fills the second lane (T5).
  - Harness: 239.71/s crafted, lanes 120/120.
  - **Confirmed in-game 2026-10-12** ("It works perfectly"). It's the first non-furnace blueprint confirmed in the user's game.
  - Its spec options (beacons, inserters per link) are what F will vary.
- **Solver `effects.py` (C):** quality, modules, beacons, research, power and demand.
  - The 2.0 whole-percent rounding was fitted on the server and matched all 476 values (F19).
  - B's measured inserter rates live in `effects.LEGENDARY_STACK_INSERTER` (F28).
  - `ratios.py` is unchanged, for the M1 generators.
- **Checks (D):** `module_validity`, `beacon_reach`, `underground_pairing` and `hidden_entities` run on every blueprint. `checks.beacon_targets(bp)` feeds `effects.entity_rates` (F24–F27).
- **Harness (A, B):**
  - Ports have `stack` (1–4), and stacked inputs are fed by script.
  - `--research all` works for M2.
  - Every inserter's items moved are counted.
  - Measurement-only `probes` script-feed or drain machines.
  - Each machine records where it unloads.
- **Machine bar:**
  - A machine fails if it's blocked on output for more than 5% of the window, unless it unloads only into other machines.
  - It also fails if its output buffer grows.
  - Idle and unpowered time are reported, not judged (P2).

**2026-10-11 (close): v2 milestone 1, the headless harness, is merged to `main`. Milestone 2 is planned but not started.**
- `main` is at `080de55`, the merge of PR #1 (steel_column, the harness and the M2 plan), plus `c0d4def`, a project-local `/secret-scan` skill. Branch `v2-m1-harness` is deleted locally and on GitHub. Tests: 187 pass and 1 is a strict xfail (`.venv/bin/pytest -q`, about 38 s).
- **The harness:** `blueprint-smith evaluate SPEC` and `build --evaluate` run a blueprint in the Linux 2.0.77 headless server (`~/.cache/blueprint-smith/`, fetched by `install-server`). A run takes about 6 s, and several can run side by side. See `docs/techniques.md` H1 and `docs/m1-harness-plan.md`.
  - **What fails a blueprint (amended P2):** crafted output under 98% of target, a machine under 95% working, a machine whose output backs up, or output that never reaches the belt end.
  - Research defaults to none so the measurements match `ratios.py`. `--research all` is available.
- **Calibration:** iron 15/s, copper 30/s and both steel samples hit exactly their target with every furnace working. The pre-T1 copper layout fills only one lane, and unwired poles fail with `no_power`. These match the in-game results.
- **M2 plan (`docs/m2-plan.md`):** the target is 240 green circuits/s on a stacked turbo belt from legendary electromagnetic plants. One legendary plant with 2 legendary beacons makes about 250/s, so the block is limited by inserters and belts, not machines. The machine bar is decided: a machine fails only when it's blocked on output.

**2026-10-11: generators. `smelting_column` is done (3 of 3 samples in-game) and `steel_column` has 1 of 3.**
- Python package `blueprint_smith` on **factorio-draftsman 3.3.1**. CLI: `build|decode|types|evaluate|install-server`. `pipeline.build(spec)` turns every draftsman warning into a failure, wires the poles, checks the declared ports, and runs the generic and per-generator checks.
- `smelting_column` (`count` or `rate`, electric furnaces) uses the user's lane-balancing layout. A west-priority splitter and a side-load every 2 furnaces fill both plate lanes (T1 in `docs/techniques.md`). Confirmed in-game on all 3 samples:
  - `examples/smelting_column.json`: iron, 15/s, yellow belt, 24 furnaces. Both lanes are full and every furnace unloads.
  - `examples/smelting_column_copper.json`: copper, 30/s, red belt, 48 furnaces. The splitter priority came out on the west half.
  - `examples/smelting_column_steel.json`: steel, 3/s from 15 iron plates/s, 24 furnaces. Every furnace unloads.
- `steel_column` (`count` of pairs or `rate` of steel/s): each iron furnace hands its plates by direct insertion to the steel furnace beside it (T4). `examples/steel_column.json` makes 3 steel/s from a full yellow belt of ore with 24 pairs, and every furnace ran in-game. Code shared by both columns lives in `generators/columns.py`.
- `docs/techniques.md` is the catalog of the user's quality bar (P), game mechanics (F) and layout techniques (T), each with its in-game status. `CLAUDE.md` makes reading it a precondition of any generator work.
- Public GitHub repo `CommanderBosko/blueprint-smith` (MIT), branch `main`, SSH remote. No linter is configured.

## Current Goals

- **Next:**
  - Open and merge the `v2-m2-f` PR.
  - Merge the follow-up PR that exempts machine-only feeders from the output-growth check (user, 2026-10-12). With it, all 8 of the optimiser's runs pass.
- **M2 done (2026-10-12):** "fill a turbo belt of green circuits" goes through `optimise` to a passing blueprint, and that pick worked in the user's game.
- **Long term:** M3 (learning from existing blueprints) and M4 (freeform placement) are stretch goals. The logistics and power & fluids generators are paused.
- **Still open from v1:** 2 more `steel_column` samples to reach the brief's 3 per type.

## Recent Decisions

- **Machines that unload only into other machines are exempt from the output-growth check too** (user, 2026-10-12). Under direct insertion, their buffer fills to a cap and then they wait, so growth can't jam anything. Before the exemption it falsely failed 2 of 8 good variants in every optimiser run; with it, all 8 pass and the pick is the same (branch `verdict-growth-exemption`).
- **Stub inserters go at the output end of the plant's edge, and the stub starts under the first one** (user, 2026-10-12, an in-game tweak that saves 2 turbo belts). The generator and `check_flow` follow it (T5).
- **F covers the optimiser and a second layout, built together** (user, 2026-10-12). The second layout is `copper: "north"`, approved from an ASCII preview over a vertically stacked alternative of the same size.
- **Variants are solver-feasible without a margin, and the harness decides the borderline ones.** `variants` keeps a spec if its `sizing` bound reaches 98% of the rate, so 1 iron inserter (87.47/s for 87.27/s) is tried even though the static 98% margin warns about it. The harness passed it.
- **Power ranks with a static estimate**, since the harness doesn't measure draw. Inserters count as an upper bound (drain plus both motions every tick, ×quality), and the estimate only breaks footprint ties.
- **Power is never judged** (user, 2026-10-12: "power is not a problem in my save"). Unpowered time is reported only. Saved to memory (`feedback_power-not-judged.md`). The harness-power-not-linked failure stays, because it guards the measurement itself.
- **A machine that unloads only into other machines isn't judged on blocking** (user, 2026-10-12). Under direct insertion, spare capacity shows as `full_output` instead of idle: the circuit block's cable plant read 55% blocked while the block delivered 240/s. A machine unloading onto a belt is still held to 5%.
- **`circuit_block` layout** (user approved, 2026-10-12): one cable plant and one circuit plant with 2 shared beacons. The second output lane comes from a side-load stub (T5), not T1's splitter, because a 4×4 plant has no rows to spare. Copper comes in stacked like iron (user).
- **Each M2 piece gets its own stacked PR** (user's choice), so each reviews on its own.
- **B's measured rates are code, held by tests.** `effects.LEGENDARY_STACK_INSERTER` is checked against the harness, so drift fails. Plant speed is held to 1e-6, not the plan's 1%, because 1% can't see the 2.0 rounding (45.45 versus 45.44 is a 0.014% difference).
- **`effects.py` is separate from `ratios.py`.** It reuses `ratios.recipe_info`, and the M1 generators keep base-speed `ratios`.
- **2.0.77 facts the checks follow** (D, confirmed headless):
  - Hidden entities are marked on their item, not the entity.
  - An underground pairs with the first same-tier underground on its line.
  - Beacon reach is the beacon's footprint grown by 3, overlapped with the machine's collision box.
  - Only a module's bonuses must be allowed.
- **v2 is a search-and-harness optimizer, not a trained ML model** (user, 2026-10-11). The request was "an ML algorithm to optimise blueprints". The interview reduced it to a solver, generator variants and a headless harness as ground truth, with ML used only where it beats those. An independent reviewer's fixes were folded in: numeric bars, footprint defined as bounding-box tiles including the belts (power breaks ties), electromagnetic plants by default, and M3 and M4 moved to stretch. Recorded in the v2 section of `PROJECT_BRIEF.md`.
- **The harness uses the free Linux headless server, not the Steam copy.** The Steam install is the Windows build under Proton. The headless 2.0.77 build needs no login. Each run gets its own write-data dir, because two instances can't share a lock file.
- **Amended P2:** a harness failure fails the build. Builds checked only statically keep throughput as `WARNING:` notes.
- **Output is judged on what the machines crafted**, not on what reaches the sink, and the measurement window scales with the slowest craft cycle.
- **The harness assumes no research by default** (M1 cases). M2 runs pass `research="all"`.
- **Blueprint strings go to the user as a file path or a `wl-copy` command, never retyped in a reply.** A hand-retyped steel string looped and came out corrupted on 2026-10-11.
- **Use draftsman 3.3.1, not 4.0.0.** 4.0.0 can't run its data lifecycle on 2.0.77: the wheel ships `compatibility/defines.lua` but `update.py` wants `compatibility/defines/2.0.lua`. `pyproject.toml` pins `<4`.
- **Warnings are failures.** Draftsman only warns on overlaps and unknown entities, so the pipeline escalates them to `BuildError`.
- **The pipeline wires poles, and `pole_network` checks the wiring.** Pasted blueprints keep only the wires they carry.
- **Flow correctness is per-generator.** The generic checks can't tell a reversed inserter from a correct one, so each generator registers its own `check_flow`.
- **Every generator is designed to use whole belts** (P1): both output lanes full, the whole input belt eaten, no machine blocked.
- Verified: directions N=0 NE=2 E=4 S=8 W=12; underground `max_distance` is 5/7/9/11 in total, not the gap; an inserter's blueprint `direction` is the side it picks up from.

## Known Issues / Tech Debt

- **Inserter rates are measured for legendary stack inserters only.** At another `quality`, `circuit_block`'s defaults and warnings use the legendary numbers, and only the harness knows.
- **The machine→machine blocking exemption hides an under-sized hand-off** (from the PR #4 review). With `cable_inserters: 1` the verdict fails only on the output rate and no longer names the cable plant or its link. F doesn't need that, because variants are sized by the solver.
- **The chosen 240/s block runs iron at 0.2% headroom:** 1 inserter carries 87.47/s against 87.27/s needed. It worked in-game on 2026-10-12. If it ever starves, the next-best variant (2 iron inserters) has the same footprint and draws 0.84 MW more.
- **The optimiser ranks by footprint and power only, so it can't see belt counts.** The user's stub tweak saved 2 belts without changing either. The generator now builds the short stub itself, but a future layout choice that only saves materials would tie on the JSON tie-break.
- **`circuit_block`'s `check_flow` doesn't check belt continuity:** a missing iron, stub or output belt tile passes statically and only the harness catches it.
- **Smaller review follow-ups:** `tests/test_ports.py` lost its exact-port-count and default-belt assertions for the M1 generators; the verdict silently exempts non-working statuses other than idle (`no_recipe`, `invalid`); `_where` and the belt stack limit (4) are duplicated across modules.
- **Untested:** whether empty or unpowered beacons count toward a machine's beacon number N (`effects.py` assumes they do), exact .5 ties in the 2.0 rounding, and mixed beacon types.
- **draftsman 3.3.1 gaps still open:** `generate_power_connections(only_axis=True)` never wires a 2×2 pole to a 1×1 pole, and `power_coverage` ignores quality's effect on pole reach, which is conservative. D covered modules, undergrounds and beacon reach.
- **The pre-T1 steel jam doesn't reproduce in the harness** (strict xfail). Low priority, because no generator builds that layout any more.
- **Copper 30/s still needs the user's in-game look** at whether the bottom furnaces are blocked. The harness says they aren't.
- **Mods gap:** the harness runs vanilla plus Space Age, but every in-game confirmation was in the user's modded game. So far the two agree, circuit block included.
- **Untested:** loading the user's mods into draftsman (it overwrites the vanilla data in the venv), and a round trip against a real blueprint from `~/.factorio/blueprint-storage-2.dat`.
- Pyright shows draftsman typing noise in the editor; runtime and pytest are fine.
- `spike/` holds throwaway scripts, including the harness spike.

## Next Steps

1. Merge `v2-m2-f` (M2 done).
2. Merge the `verdict-growth-exemption` PR.
3. For the user, in-game: re-check copper 30/s for blocked bottom furnaces, and run 2 more `steel_column` samples (a full red belt of ore at 6 steel/s with 48 pairs, and a small odd count such as 5 pairs).
