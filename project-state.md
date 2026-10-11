# Project State

## Current Project State

**2026-10-11 — First generator done: all 3 smelting samples confirmed in-game. Second generator (`steel_column`) works in-game (1 of 3 samples)**
- Python package `blueprint_smith` (src layout, `.venv`, editable install) on **factorio-draftsman 3.3.1**. 73 tests pass (`.venv/bin/pytest -q`).
- CLI: `blueprint-smith build|decode|types`. `pipeline.build(spec)` turns every draftsman warning into a failure, adds copper wires between poles, and runs generic checks (inserter wiring, pole coverage, pole network) plus per-generator checks.
- One generator: `smelting_column` (`count` or `rate`, electric-furnace only). Since 2026-10-11 it uses the user's lane-balancing layout: a west-priority splitter and side-load every 2 furnaces fill both plate lanes (technique T1 in `docs/techniques.md`).
- Second generator: `steel_column` (`count` of pairs or `rate` of steel/s). Iron ore goes into an iron furnace, which hands its plates by direct insertion to a steel furnace beside it (T4 in `docs/techniques.md`). One iron furnace makes exactly what one steel furnace eats. `examples/steel_column.json`: 3 steel/s from a full yellow belt of ore, 24 pairs. **Confirmed in-game 2026-10-11: every furnace running.** Shared code for both columns lives in `generators/columns.py`.
- **Techniques catalog:** `docs/techniques.md` collects the user's quality bar, game mechanics and layout techniques, each with its in-game status. `CLAUDE.md` says to read it before any generator work and to update it whenever the user teaches something.
- **In-game (2026-10-11), lane-balanced layout: all 3 samples pass the brief's bar and the user's whole-belt bar.** This meets the brief's "done" for `smelting_column`.
  - `examples/smelting_column_copper.json`: copper, 30/s, fast belt, 48 furnaces. Came out correctly, with splitter priority on the west half.
  - `examples/smelting_column.json`: iron, 15/s, yellow belt, 24 furnaces (raised from 7.5/s to use the whole belt). Both plate lanes 100% full, and every furnace can unload.
  - `examples/smelting_column_steel.json`: steel, 3/s from 15 iron plates/s, 24 furnaces. Every furnace can unload; the bottom-furnace blocking from the old layout is gone.
- **In-game (2026-10-11), old single-sided layout:** all 3 sample specs passed the brief's bar (import cleanly, flow correctly, fully powered, run at the specified rate), but samples 2 and 3 were inefficient.
  - Iron: 12 furnaces, iron plate, 7.5/s, yellow belt (the sample is now 15/s).
  - Copper: 24 furnaces, copper plate, 15/s, fast belt (72 tiles tall). Ate only half of a full red belt of ore. `examples/smelting_column_copper.json` is now the full red belt version (30/s, 48 furnaces, 144 tiles tall).
  - `examples/smelting_column_steel.json`: 24 furnaces, steel, 3/s from 15 iron plates/s. Ate the full yellow input belt, but the last few furnaces couldn't unload because the far lane of the plate belt was full.
- Public GitHub repo `CommanderBosko/blueprint-smith` (MIT), branch `main`, SSH remote. No linter configured.

**2026-10-11: v2 milestone 1, the headless evaluation harness, works.**
- `blueprint-smith evaluate SPEC` and `build --evaluate` run a blueprint in a real Factorio 2.0.77 headless server (Linux build, in `~/.cache/blueprint-smith/`) and fail on the amended P2 bar.
- It is calibrated against every in-game result: all 4 samples pass at exactly their target, pre-T1 copper shows one lane, and unwired poles fail.
- Open: the pre-T1 steel jam doesn't reproduce, and copper 30/s is still awaiting the user's in-game re-check.
- 188 tests (1 strict xfail). See `docs/techniques.md` H1 and `docs/m1-harness-plan.md`.

## Current Goals

- **Short term (next 1-3 sessions):** v2 optimizer milestone 1, the headless evaluation harness (`PROJECT_BRIEF.md`, v2 section, confirmed 2026-10-11). Still open from v1: 2 more `steel_column` samples.
- **Long term:** v2 milestone 2 (module/beacon solver, beaconed green circuits, an optimiser scored by the harness); M3/M4 are stretch goals. Logistics and power & fluids generators are paused.

## Recent Decisions

- **Use draftsman 3.3.1, not 4.0.0.** 4.0.0 can't run its data lifecycle on installed 2.0.77: the wheel ships `compatibility/defines.lua` but `update.py` wants `compatibility/defines/2.0.lua`, and a copied 2.1 defines file then fails on `defines.default_icon_size`. `pyproject.toml` pins `<4`.
- **Warnings are failures.** Draftsman only warns on overlaps and unknown entities, so the pipeline escalates them to `BuildError`.
- **The pipeline wires poles; `pole_network` checks it.** Pasted blueprints only keep the wires they carry, so the game won't join poles inside one. The first in-game import had no wires and 11 of 12 poles were dead, even though they were within reach (6 tiles apart, reach 9). The pipeline now calls `generate_power_connections(only_axis=True)`. Every build fails if a pole is outside the main network or a wire is longer than its poles' reach.
- **Flow correctness is per-generator.** The generic checks can't tell a reversed inserter from a correct one (found by a mutation test), so each generator registers its own `check_flow`.
- **In-game samples are judged on belt use too.** "Runs at the specified rate" isn't enough for the user: both output lanes should fill, the full input belt should be eaten, and no machine should be blocked from unloading. Design every generator to use whole belts.
- **Steel from ore uses direct insertion, as a separate generator** (user's choice, 2026-10-11). `smelting_column` keeps its plate-fed steel option for when plates come from elsewhere.
- **Fixed: `power_coverage` measured pole reach from the pole's edge instead of its centre** (half a tile too generous for medium poles, a whole tile for big ones). It never misfired on the smelting column, but it would have passed a steel column with no middle pole. Found by a mutation test; regression tests cover small, medium and big poles.
- **Two-tier acceptance.** Guaranteed: valid string, round-trip, no collisions, connected, powered, ratios computed. Best-effort: real throughput, reported as `WARNING:` notes.
- Verified from prototype data: directions N=0 NE=2 E=4 S=8 W=12; underground `max_distance` 5/7/9 (total, not gap); an inserter's blueprint `direction` is the side it picks up from.

## Known Issues / Tech Debt

- **Untested:** loading the 65 mods (`draftsman -m ~/.factorio/mods update` would overwrite the vanilla data pickles in the venv, so it's re-runnable but not free); round trip against a real blueprint from `~/.factorio/blueprint-storage-2.dat`.
- **Fixed 2026-10-11: the old single-sided column put every plate on one lane** (output capped at one lane, half the input belt went unused, the last furnaces were blocked). Replaced by lane balancing; see T1 in `docs/techniques.md`. Confirmed to fill a whole yellow belt with no blocked furnaces (iron 15/s). Faster belts and longer columns aren't checked yet.
- Ratio math covers base crafting speed only: no modules, beacons or quality yet.
- Pyright shows stale "import could not be resolved" errors in the editor; runtime and pytest are fine (`pyrightconfig.json` exists).
- `spike/` holds throwaway scripts; delete or keep as reference.

## Next Steps

1. 2 more `steel_column` samples (for example a full red belt of ore at 6 steel/s, and a small odd count) to meet the brief's 3 per type.
2. Pick the next generator: assembler line vs. first logistics piece.
3. Try mod loading and the real-blueprint round trip.
