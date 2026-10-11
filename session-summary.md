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
