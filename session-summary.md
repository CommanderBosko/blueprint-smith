## Session: 2026-10-12 — M2 pieces A–E: harness, solver, checks, measured rates, circuit block

**Focus**: Build M2 up to the green circuit block, piece by piece: A, C and D in parallel, then B, then E.

### What changed (and why)
- **A, C, D (sub-agents in parallel):**
  - A: the harness feeds stacked belts by script (loaders can't stack), runs with all research, and applies the new machine bar.
  - C: `effects.py` models quality, modules, beacons and research. Its fit of 2.0's whole-percent rounding on the server matched 476 of 476 values.
  - D: new generic checks for modules, beacon reach, underground pairing and hidden entities, each confirmed against the server.
- **B:** micro-blueprints with script-fed machines measured one legendary stack inserter: 87.47/s from a stacked belt, 120/s plant to plant, 80/s onto a lane (2 fill it to 120). The solver matches the harness to 1e-6.
- **E:** `circuit_block`, the layout the user approved. A side-load stub fills the second output lane (T5). It makes 240/s in the harness, and the user confirmed it in-game: "It works perfectly".

### Decisions
- Power is never judged: the user's save has plenty (user).
- A machine that unloads only into other machines isn't judged on blocking: under direct insertion, spare capacity shows as blocked instead of idle (user).
- Copper input stacked like iron (user). Each piece gets its own stacked PR (user).
- B's rates are stored in `effects.py` and held to the harness by tests.

### Issues / surprises
- `products_finished` counts crafts (bonus crafts included), not items. It was recorded wrong yesterday; F18 is fixed.
- Inserters' pick-up and drop targets aren't set until they've run, so the mod reads where machines unload at the end of the window.
- The plan's 1% solver tolerance couldn't see the 2.0 rounding, so plant speed is held to 1e-6.
- Two cleanup commands were denied. The user deleted the leftover run dirs.
- Secret scan (project `/secret-scan`): clean across the tree and all 14 commits.

### Next session
- Merge PRs #2 → #3 → #4.
- Decide F's scope (tune one layout, or add a second first), then build the optimiser.

**Commits**: `e17499d..0c7c24c` (5 commits, on the stacked PR branches)

---

## Session: 2026-10-11 (afternoon) — Repo, lane balancing, steel_column, headless harness, M2 plan

**Focus**: Finish the smelting samples in-game, add steel from ore, then turn "an ML algorithm to optimise blueprints" into a scoped v2 and build its first milestone.

This close spans several sessions since the previous close, which ran before `git init`.

### What changed (and why)
- **Repo:** `git init` and a public MIT repo, `CommanderBosko/blueprint-smith`.
- **Spec bugs from probing edge cases:** a furnace accepted recipes it can't craft. The input-belt warning ignored ingredient amounts (steel at 4/s needs 20 plates/s). Malformed specs crashed instead of exiting 2.
- **Lane balancing (T1):** an inserter drops only onto a belt's far lane, so the old column filled one lane and blocked its last furnaces in-game. The user showed a layout with a west-priority splitter and a side-load every 2 furnaces. All 3 smelting samples then passed in-game at full belt. `docs/techniques.md` became the catalog of everything learned, and `CLAUDE.md` now requires reading it first.
- **`steel_column`:** the user wanted steel made from ore. Each iron furnace feeds the steel furnace beside it by direct insertion, at an exact 1:1 rate. It ran in-game with every furnace working. Adding it exposed a bug: `power_coverage` measured pole reach from the pole's edge instead of its centre.
- **v2 brief:** the interview and an independent review turned the ML request into a search-and-harness optimizer. ML is used only where it beats search or the solver. The confirmed brief is in the v2 section of `PROJECT_BRIEF.md`.
- **M1, the headless harness:** a Linux 2.0.77 headless server pastes, feeds, powers and measures a blueprint in about 6 s. It reproduces every in-game result except the pre-T1 steel jam.
- **M2 planned:** `docs/m2-plan.md`. One legendary electromagnetic plant with 2 beacons makes about 250 circuits/s, so the 240/s block is limited by inserters and belts.
- **Shipped:** PR #1 merged with a merge commit, and the feature branch deleted.
- **Secret scan:** this close added a `/secret-scan` skill and ran it. Tree and history are clean.

### Decisions
- The harness uses the Linux headless server, because the Steam copy is the Windows build under Proton.
- Amended P2: a harness failure fails the build.
- Output is judged on what the machines crafted. Two extra failures: a machine whose output backs up, and output that never reaches the belt end.
- The harness assumes no research by default; with everything researched, steel productivity research adds 10%.
- M2 machine bar (user): fail only when blocked on output, because beacon steps make exact sizing impossible.

### Issues / surprises
- A blueprint string retyped by hand into a reply looped and came out corrupted. Strings now go out only as file paths or `wl-copy` commands.
- The pre-T1 steel jam seen in-game doesn't reproduce in the harness (strict xfail).
- Loaders can't output stacked items, so M2's harness has to feed stacked belts by script.
- The transcript scan was misleading at first: piping it through `head -c` cut it off, and a relative project path made it fall back to one transcript.

### Next session
- M2 pieces A (harness), C (solver) and D (checks) in parallel, then B, E and F.
- In-game, for the user: re-check copper 30/s for blocked bottom furnaces, and run 2 more `steel_column` samples.

**Commits**: `9a03f8a..c0d4def` (8 commits, including the PR #1 merge)

---

## Session: 2026-10-11 — First in-game test; pole wiring fix

**Focus**: Import the smelting column in-game and fix what broke.

### What changed (and why)
- The first in-game import worked: the column builds, belts flow south, and the inserters move ore → furnace → plate belt. But 11 of 12 poles had no power.
- The cause was missing copper wires, not spacing (6 tiles apart, reach 9 per `entities.lua`). A pasted blueprint only keeps the wires it carries, so the game doesn't join poles inside one. The pipeline now calls `generate_power_connections(only_axis=True)` (a ladder: 16 wires for 12 poles). The new generic check `pole_network` fails any build with an unwired pole or a wire past reach. 3 new tests, 19 passing.
- Re-imported the fixed string in-game: fully wired, everything powered.

### Decisions
- Wire in the pipeline (works for every generator) rather than per generator. Axis-only wiring keeps the grid tidy, and `pole_network` catches any pole that leaves out.

### Issues / surprises
- Our checks tested pole *coverage* but never pole-to-pole *wiring*, so the gap only showed up in-game.
- The user asked to commit at the end, but the project still isn't a git repo. Paused before `git init`, at the user's request.

### Next session
- `git init -b main` and a first commit (asked for, not done yet).
- 2 more in-game sample specs for `smelting_column`, then pick the next generator.

**Commits**: none (not a git repo yet)

---

## Session: 2026-09-29 — Scoping, research, draftsman spike, first generator

**Focus**: Decide whether Claude can craft Factorio blueprints, pin down scope, and get a working generator pipeline.

### What changed (and why)
- Interviewed for scope; an independent reviewer found the first brief weak (untestable "done", too much for v1). Revised into `PROJECT_BRIEF.md`: production lines first, two-tier acceptance, mods as a stretch goal.
- Researched the format, data extraction, geometry, ratio math and libraries with 16 parallel reviewers; saved to memory. Main result: build on factorio-draftsman rather than from scratch.
- Ran a spike, then scaffolded `blueprint_smith` (CLI, pipeline, checks, `smelting_column` generator, 14 tests).

### Decisions
- draftsman **3.3.1**, not 4.0.0 (4.0.0 can't load 2.0.77 data; details in `project-state.md`).
- Draftsman warnings become build failures.
- Generators own their flow checks after a mutation test showed reversed inserters slipping through.

### Issues / surprises
- `Blueprint(s)` treats the string as the label; use `Blueprint.from_string(s)`.
- Wiki said underground reach 4/6/8; prototype data says 5/7/9.
- Yellow-belt plate output tops out at 12 furnaces because inserters only fill one lane.
- Project isn't a git repo, so nothing was committed or pushed at close.

### Next session
- Import the smelting column in-game and report results; fix what breaks.
- Choose the next generator; test mods; `git init`.

**Commits**: none (not a git repo)

---
