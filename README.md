# Blueprint Smith

Generates importable Factorio 2.0 + Space Age blueprint strings from JSON specs. A Python CLI builds the layout with [factorio-draftsman](https://github.com/redruin1/factorio-draftsman), validates it, and encodes the string. Built to be driven by Claude Code, but usable by hand.

## Current Status

Early prototype. One generator (`smelting_column`) builds, passes its tests, and is confirmed working in-game (imports, flows, fully powered) as of 2026-10-11. See `project-state.md` for detail and `session-summary.md` for history.

## Features

- Build a blueprint string from a JSON spec (`count` or target `rate`)
- Decode any blueprint string back to JSON
- Every draftsman warning (overlap, unknown entity) fails the build
- Static checks: inserter pickup/drop wiring, pole coverage, per-layout flow direction
- Throughput limits reported as warnings (best-effort, not proven)

## Getting Started

Prerequisites: Python 3.10+, Factorio 2.0.x (with Space Age) installed.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/draftsman -p <Factorio install>/data update --no-mods   # load game data into draftsman
.venv/bin/blueprint-smith build examples/smelting_column.json
```

Use `factorio-draftsman<4`: version 4.x cannot load 2.0.x game data. Run tests with `.venv/bin/pytest -q`.

## Project Structure

- `src/blueprint_smith/` — pipeline, checks, ratio math, CLI, and `generators/`
- `tests/` — pytest suite
- `examples/` — sample specs
- `PROJECT_BRIEF.md` — confirmed scope; `CLAUDE.md` — guidance for Claude Code

## Recent Changes

- **2026-10-11** — First in-game test passed after a fix: the pipeline now wires power poles together, and a new `pole_network` check fails any unwired pole (19 tests).
- **2026-09-29** — Scaffolded the package, CLI and pipeline; added the `smelting_column` generator and 14 tests.

## Roadmap

Production lines first, then logistics, then power & fluids. Mod support is a stretch goal. See `PROJECT_BRIEF.md`.

## License

MIT. See `LICENSE`.
