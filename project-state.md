# Project State

## Current Project State

_Older blocks are in [project-state-archive.md](project-state-archive.md)._

**2026-10-13 (close): M2c is scoped. The user confirmed its brief (`docs/m2c-brief.md`) after an interview and an independent review. No code changed.**
- **M2c:** `plant_array` for any machine and any one-item intermediate. `optimise` with just an item and a rate tries each capable electric machine (assembler 1/2/3, EM plant, electric furnace, the foundry for belts) and every one-item ingredient that can be made in-block, and footprint picks. Stone and steel furnaces only on request, with fuel on a belt.
- **Done test:** `optimise {"item": "automation-science-pack", "rate": 240}` passes the harness and the user's in-game check. Seven proof requests pass the harness at 4+ product machines a row, and every in-scope recipe builds statically. The red and green blocks and their picks don't change.
- **Docs:** `PROJECT_BRIEF.md`'s v2 section has an M2c summary and done criteria. `CLAUDE.md`'s Status points at M2c, and its stale "commit and PR `v2-red-circuits`" line is fixed.
- **Tests:** unchanged, 644 pass and 1 is a strict xfail (no code touched).

**2026-10-12 (close): M2, M2b and CI are all merged to `main` (`6f24bcf`), and CI is green. The user picked the next milestone, generalising `plant_array`, but paused its scoping interview before the first question.**
- **Merged since the last close** (all with merge commits; only `main` is left, locally and on GitHub):
  - #6: the project's `/ingame-test` skill, plus a tighter `/secret-scan`.
  - #7: piece F, the optimiser.
  - #8: the output-growth exemption for machines that feed only machines.
  - #9: M2b, the red circuit plant array, input labels and output balancers.
  - #10: CI.
- **CI (`.github/workflows/ci.yml`)** runs on every push to `main` and every PR. The first run on `main` passed all three jobs:
  - `lint` (ruff, errors only) and `quick` (`-m "not harness"`) run on GitHub's runners.
  - `harness` runs the full suite on the self-hosted runner `factorio`, on the user's gaming machine: 644 passed, 1 xfailed.
- **The runner** is defined in `~/NixOS/hosts/gaming/github-runner.nix`, committed there as `3f3cf9e`. Jobs run as a sandboxed dynamic user with no `/home`, apart from the server dir mounted read-only, and they find the server through `$BPS_FACTORIO_SERVER`. `BPS_REQUIRE_HARNESS=1` fails any skipped test.
  - A PR from a fork waits for the user's approval before any workflow runs, for anyone without write access (`all_external_contributors`).
- **Golden snapshots (`tests/test_confirmed.py`):** 7 fixtures pin every in-game-confirmed layout entity for entity, wires included. They run in about 3 s with no harness. To re-pin: `BPS_UPDATE_SNAPSHOTS=1`.
- **Next milestone (user, 2026-10-12):** make `plant_array` take any machine and any in-block intermediate. Today it only handles electromagnetic plants with copper cable. Nothing is settled yet: the why, the done-test recipe, the rate, and whether the red block must stay identical. The facts gathered for the interview are in memory (`project_next-milestone-plant-array.md`).
- **Tests:** 644 pass and 1 is a strict xfail (`.venv/bin/pytest -q`).

**2026-10-12 (latest): M2b is done (merged as PR #9). `blueprint-smith optimise` turns "fill a turbo belt of red circuits" into a two-row plant array that passes the harness and ran at 240/s in the user's game.**
- **In-game spot-check (2026-10-12):** "It shows 240.5/s with both lanes full. The balancer works. The display panels are placed perfectly." The Rate Calculator's 240.5/s is exactly the solver's 2 × 120.27 (F19, F21, F24).
- **`plant_array`:** generic over the recipe. Each red plant gets cable by direct insertion from a cable plant beside it, two mirrored rows share one beacon row, and the cable plants reach copper with long-handed inserters (T7–T10). It's 42×21 before the pipeline's ends.
- **The user's in-game copy cut resources in three places, now in the generator** (their exported string, diffed tile by tile: the generated block matches it entity for entity):
  - copper hops under both near belts in one go;
  - row B's near items merge as they surface;
  - both outputs side-load a middle belt.
  - That's 4 undergrounds and 5 belts fewer.
- **Every block now gets two ends from the pipeline:** a display panel showing each input's item, 2 tiles out (P3), and a lane balancer after each belt output (P4, T11). Both are the user's, both are confirmed in-game, and both apply to all four generators.
- **Then a fourth change, the lane reset (T12):** the user saw the output inserters waiting on a full lane and added T1's priority splitter and side-load halfway along each output belt. It's in the generator, which matches their blueprint entity for entity.
- **Harness:** 240.55/s crafted, 240.00/s delivered, lanes 120.00/120.00, no red plant blocked. Before the reset it was 238.09/s with 1.1% blocked.
- **1 output inserter a plant is enough with the reset** (user, in-game, 2026-10-12). The harness's growth bar had failed it on 4 items, which over 6× the window turned out to be a 16-item hand's swing, not a backlog. The bar now allows for the biggest hand unloading a machine, and `optimise` picks 1 a plant (8 stack inserters fewer).
- **Tests:** 631 pass and 1 is a strict xfail (`.venv/bin/pytest -q`, about 140 s).

**2026-10-12 (later): M2 piece F, the optimiser, is built on branch `v2-m2-f`. `blueprint-smith optimise` turns "fill a turbo belt of green circuits" into an 11×11 blueprint that passes the harness, and it worked in the user's game. That completes M2's definition of done. F is merged (PR #7).**
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

## Current Goals

- **Next: M2c** (`docs/m2c-brief.md`, confirmed 2026-10-13): `plant_array` for any non-fluid machine and any one-item intermediate. Write its plan first.
- **Deferred, each required eventually** (user: "You're going to have to be ready for anything"): fluids, fission, fusion, Gleba, intermediates made from 2+ items and chains of them, arrays with no intermediate, 3+ near items, and a second plant-array layout.
- **CI done (2026-10-12):** every push to `main` and every PR runs lint, the quick tests and the full harness suite. Snapshots pin each in-game-confirmed layout.
- **M2b done (2026-10-12):** "fill a turbo belt of red circuits" goes through `optimise` to a passing plant array, and it ran at 240/s in the user's game.
- **M2 done (2026-10-12):** "fill a turbo belt of green circuits" goes through `optimise` to a passing blueprint, and that pick worked in the user's game.
- **Long term:** M3 (learning from existing blueprints) and M4 (freeform placement) are stretch goals. The logistics and power & fluids generators are paused.
- **Still open from v1:** 2 more `steel_column` samples to reach the brief's 3 per type.

## Recent Decisions

- **M2c's scope** (user, 2026-10-12/13, every decision confirmed explicitly; full list in `docs/m2c-brief.md`):
  - **Why:** toward the v2 goal, plain-word requests for more products without a generator per recipe.
  - **Machines:** any non-fluid electric machine. I'd recommended just assembler 3 + EM plant. Burner furnaces only when asked, never a default. P and K may be different machines and sizes.
  - **In-block intermediate:** the optimiser tries every qualifying one-item ingredient, smelted ones included, against my recommendation of plates on belts. So the science pick may ask for copper ore, and done 1 doesn't pin gears.
  - **Machine:** footprint picks, v2's rule. Speed-3 goes in machines whose recipe refuses productivity (F25).
  - **Layout:** stays P > K < P. Whether to add a second layout (one K feeding many) is decided from a comparison report, and if it comes, it's the next milestone.
  - **Regression:** existing confirmed fixtures, the red pick and the green pick (`circuit_block`'s 11×11) don't change. A science fixture is added after the in-game check.
  - **Proof:** 7 harness requests at 4+ product machines a row, a static build of every in-scope recipe, and only science in-game.
- **The next milestone is generalising `plant_array`** (user, 2026-10-12). The alternatives passed over were unpausing fluids, scoping M3/M4, and having the harness load the user's mods.
- **The harness job runs on a self-hosted runner** (2026-10-12), because factorio.com answers 403 to the server download from GitHub's runners. Lint and the quick tests stay on GitHub's runners.
- **Runner jobs can't act as the user** (from the NixOS session's review of the runner spec, agreed 2026-10-12). A fork's PR can edit `ci.yml`, including an `if:` guard, so the guard alone isn't enough. Jobs therefore run as a sandboxed dynamic user that sees only a read-only server dir, and fork PRs need approval. That's why tests must never find game files through `Path.home()`.
- **A skipped harness test fails CI** (`BPS_REQUIRE_HARNESS=1`). Without the server, a plain `pytest` passed with all 55 harness tests skipped.
- **Confirmed layouts are pinned by golden snapshots.** A change can keep every property test green and still move a confirmed block, and the snapshots catch that. Re-pinning means re-testing in-game too (`docs/techniques.md` checklist item 8).
- **Ruff gates errors only** (`E4,E7,E9,F`). Pyright isn't gated, because most of its ~78 errors come from draftsman's types.
- **The output-growth bar allows for the biggest hand unloading a machine** (user, 2026-10-12, choosing to make 1 output inserter a plant the default after it worked in-game): a flowing machine's result slots swing by up to that hand.
- **Every input gets a display panel showing its item, 2 tiles out with one free tile between** (P3, user, 2026-10-12, from a screenshot of their own build). The pipeline adds them; they're left out of port tiles, the footprint and the harness's box.
- **Every belt output ends in a lane balancer** (P4/T11, user, 2026-10-12): a splitter, then both halves side-load the middle belt from opposite sides. The pipeline adds it and moves the output port to its end. Generator checks judge the generator's layout before the ends are added.
- **Spend undergrounds and belts sparingly** (user, 2026-10-12, their in-game copy of the red block): one hop under many belts, not many under one; merge two items as soon as they sit side by side (T8); merge two outputs by side-loading from both sides (T9). It's checklist item 12 in `docs/techniques.md`.
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

1. Write the M2c plan (like `docs/red-circuits-plan.md`): numbers from the solver for science and each proof request, the generalised geometry, how fuel reaches burner Ks, furnace roles in `check_flow`, a work breakdown with parallel pieces, and a verification plan. Get the user's OK before any code.
2. Settle in the plan the brief's open risks: mixed machine sizes from 2×2 to 5×5 while the red block stays identical, inserter rates measured only for EM plants, and the optimiser's run cap with many more variants.
3. For the user, in-game: re-check copper 30/s for blocked bottom furnaces, and run 2 more `steel_column` samples (a full red belt of ore at 6 steel/s with 48 pairs, and a small odd count such as 5 pairs).
