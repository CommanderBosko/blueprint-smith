# Project State Archive

Older `Current Project State` blocks rotated out of [project-state.md](project-state.md) by session-closer, most recent first. Git history holds every pre-rotation version of that file.

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

