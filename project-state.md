# Project State

## Current Project State

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

- **Next session:** start M2 from `docs/m2-plan.md` with pieces A, C and D in parallel:
  - **A (harness):** stacked input feeding with `insert_at_back`, research-all runs, and the blocked-only machine bar.
  - **C (solver):** quality, module, beacon and research maths in `effects.py`.
  - **D (checks):** module validity, beacon reach, underground pairing, hidden entities.
- **Then:** B (measured legendary stack-inserter rates), E (the `circuit_block` generator) and F (the optimiser).
- **Long term:** the M2 end goal. "Fill a turbo belt of green circuits" should produce a beaconed electromagnetic-plant blueprint that passes the harness. The optimiser returns the smallest passing footprint, and the user spot-checks it in-game. M3 (learning from existing blueprints) and M4 (freeform placement) are stretch goals. The logistics and power & fluids generators are paused.
- **Still open from v1:** 2 more `steel_column` samples to reach the brief's 3 per type.

## Recent Decisions

- **v2 is a search-and-harness optimizer, not a trained ML model** (user, 2026-10-11). The request was "an ML algorithm to optimise blueprints". The interview reduced it to a solver, generator variants and a headless harness as ground truth, with ML used only where it beats those. An independent reviewer's fixes were folded in: numeric bars, footprint defined as bounding-box tiles including the belts (power breaks ties), electromagnetic plants by default, and M3 and M4 moved to stretch. Recorded in the v2 section of `PROJECT_BRIEF.md`.
- **The harness uses the free Linux headless server, not the Steam copy.** The Steam install is the Windows build under Proton. The headless 2.0.77 build needs no login. Each run gets its own write-data dir, because two instances can't share a lock file.
- **Amended P2:** a harness failure fails the build. Builds checked only statically keep throughput as `WARNING:` notes.
- **Output is judged on what the machines crafted**, not on what reaches the sink, and the measurement window scales with the slowest craft cycle. Two failures were added beyond the confirmed bar, because a blocked furnace keeps crafting into a 100-plate buffer and reads "working" for minutes: a machine whose output backs up, and output that never reaches the belt end.
- **The harness assumes no research by default.** With everything researched, Space Age's steel productivity research adds 10% to every steel result, which the ratio maths doesn't model.
- **M2 scope (user, 2026-10-11):** iron and copper plates come in, the block makes its own cable, the output is 240/s on a stacked turbo belt, and everything is researched. Machines fail only when **blocked on output** for more than 5% of the window. Beacon steps make exact sizing impossible (a cable plant with 1 beacon is about 73% busy), so idle over-capacity is reported as utilisation, not failed.
- **PR #1 was merged with a merge commit** so the three commits kept their SHAs and detailed messages on `main`.
- **Blueprint strings go to the user as a file path or a `wl-copy` command, never retyped in a reply.** A hand-retyped steel string looped and came out corrupted on 2026-10-11.
- **Steel from ore uses direct insertion, as a separate generator** (user's choice, 2026-10-11). `smelting_column` keeps its plate-fed steel option.
- **Use draftsman 3.3.1, not 4.0.0.** 4.0.0 can't run its data lifecycle on 2.0.77: the wheel ships `compatibility/defines.lua` but `update.py` wants `compatibility/defines/2.0.lua`. `pyproject.toml` pins `<4`.
- **Warnings are failures.** Draftsman only warns on overlaps and unknown entities, so the pipeline escalates them to `BuildError`.
- **The pipeline wires poles, and `pole_network` checks the wiring.** Pasted blueprints keep only the wires they carry. The first in-game import had no wires, and 11 of 12 poles were dead.
- **Flow correctness is per-generator.** The generic checks can't tell a reversed inserter from a correct one, so each generator registers its own `check_flow`.
- **Every generator is designed to use whole belts** (P1): both output lanes full, the whole input belt eaten, no machine blocked.
- **`power_coverage` measures reach from the pole's centre.** It used the pole's edge before, which was half a tile too generous for medium poles.
- Verified from prototype data: directions N=0 NE=2 E=4 S=8 W=12; underground `max_distance` is 5/7/9 in total, not the gap; an inserter's blueprint `direction` is the side it picks up from.

## Known Issues / Tech Debt

- **The pre-T1 steel jam doesn't reproduce in the harness** (strict xfail). In the user's game the last furnaces couldn't unload; in the harness every furnace works, even after 20 minutes. Possible causes: a backed-up consumer, the startup burst, or a mod. Low priority, because no generator builds that layout any more.
- **Copper 30/s still needs the user's in-game look** at whether the bottom furnaces are blocked. The harness says they aren't.
- **Mods gap:** the harness runs vanilla plus Space Age, but every in-game confirmation was in the user's modded game.
- **The calibration set is all furnaces.** There's no ground truth for assemblers, modules or beacons until M2's measured primitives and the user's spot-check.
- **draftsman 3.3.1 gaps M2 must cover itself:** it doesn't validate modules, doesn't check underground pairing or distance, and has no beacon-reach helper. `generate_power_connections(only_axis=True)` never wires a 2×2 pole to a 1×1 pole, and it ignores quality's effect on pole reach.
- **Loaders can't output stacked items, and the turbo loader is hidden.** The harness has to feed stacked belts by script (piece A).
- Leftover temp dir `/tmp/bps-spike-wuxnvy3_` (about 750 KB) from the M1 spike is safe to delete. The cleanup command was denied during the session.
- **Untested:** loading the user's mods into draftsman (it overwrites the vanilla data in the venv), and a round trip against a real blueprint from `~/.factorio/blueprint-storage-2.dat`.
- Ratio maths uses base crafting speed only. M2 piece C adds modules, beacons and quality.
- Pyright shows stale "import could not be resolved" errors in the editor; runtime and pytest are fine.
- `spike/` holds throwaway scripts, including the harness spike.

## Next Steps

1. M2 pieces A, C and D in parallel, each on its own file boundary from the work breakdown in `docs/m2-plan.md`.
2. Piece B (measured inserter rates and beacon speed in the harness) once A lands. Then E (the generator) and F (`blueprint-smith optimise`).
3. For the user, in-game: re-check copper 30/s for blocked bottom furnaces, and run 2 more `steel_column` samples (a full red belt of ore at 6 steel/s with 48 pairs, and a small odd count such as 5 pairs).
4. Delete `/tmp/bps-spike-wuxnvy3_`.
