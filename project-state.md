# Project State

## Current Project State

**2026-10-11 — First generator confirmed working in-game**
- Python package `blueprint_smith` (src layout, `.venv`, editable install) on **factorio-draftsman 3.3.1**. 19 tests pass (`.venv/bin/pytest -q`).
- CLI: `blueprint-smith build|decode|types`. `pipeline.build(spec)` turns every draftsman warning into a failure, adds copper wires between poles, and runs generic checks (inserter wiring, pole coverage, pole network) plus per-generator checks.
- One generator: `smelting_column` (`count` or `rate`, electric-furnace only).
- **In-game (2026-10-11):** `examples/smelting_column.json` (12 furnaces, iron plate, 7.5/s) imports cleanly, flows correctly, and is fully powered. That is 1 of the ~3 sample specs the brief needs per type.
- Public GitHub repo `CommanderBosko/blueprint-smith` (MIT), branch `main`, SSH remote. No linter configured.

## Current Goals

- **Short term (next 1-3 sessions):** finish in-game samples for the smelting column; then build the second production-line generator (assembler line) or the first logistics piece; test mod loading.
- **Long term:** production lines, logistics, then power & fluids (see `PROJECT_BRIEF.md`); mods as a stretch goal.

## Recent Decisions

- **Use draftsman 3.3.1, not 4.0.0.** 4.0.0 can't run its data lifecycle on installed 2.0.77: the wheel ships `compatibility/defines.lua` but `update.py` wants `compatibility/defines/2.0.lua`, and a copied 2.1 defines file then fails on `defines.default_icon_size`. `pyproject.toml` pins `<4`.
- **Warnings are failures.** Draftsman only warns on overlaps and unknown entities, so the pipeline escalates them to `BuildError`.
- **The pipeline wires poles; `pole_network` checks it.** Pasted blueprints only keep the wires they carry, so the game won't join poles inside one. The first in-game import had no wires and 11 of 12 poles were dead, even though they were within reach (6 tiles apart, reach 9). The pipeline now calls `generate_power_connections(only_axis=True)`. Every build fails if a pole is outside the main network or a wire is longer than its poles' reach.
- **Flow correctness is per-generator.** The generic checks can't tell a reversed inserter from a correct one (found by a mutation test), so each generator registers its own `check_flow`.
- **Two-tier acceptance.** Guaranteed: valid string, round-trip, no collisions, connected, powered, ratios computed. Best-effort: real throughput, reported as `WARNING:` notes.
- Verified from prototype data: directions N=0 NE=2 E=4 S=8 W=12; underground `max_distance` 5/7/9 (total, not gap); an inserter's blueprint `direction` is the side it picks up from.

## Known Issues / Tech Debt

- **Untested:** loading the 65 mods (`draftsman -m ~/.factorio/mods update` would overwrite the vanilla data pickles in the venv, so it's re-runnable but not free); round trip against a real blueprint from `~/.factorio/blueprint-storage-2.dat`.
- Plate belt in the smelting column only fills one lane, so yellow belt caps at 12 electric furnaces (7.5/s). A larger column builds but warns.
- Ratio math covers base crafting speed only: no modules, beacons or quality yet.
- Pyright shows stale "import could not be resolved" errors in the editor; runtime and pytest are fine (`pyrightconfig.json` exists).
- `spike/` holds throwaway scripts; delete or keep as reference.

## Next Steps

1. Two more in-game sample specs for `smelting_column` (e.g. copper/steel/stone via `rate`, a faster belt) to meet the brief's ~3-per-type bar.
2. Pick the next generator: assembler line vs. first logistics piece.
3. Try mod loading and the real-blueprint round trip.
