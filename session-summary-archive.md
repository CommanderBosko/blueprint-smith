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
