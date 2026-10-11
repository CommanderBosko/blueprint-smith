# Blueprint Smith

Generates importable Factorio 2.0 + Space Age blueprint strings from JSON specs. A Python CLI builds the layout with [factorio-draftsman](https://github.com/redruin1/factorio-draftsman), validates it, and encodes the string. It can also run the blueprint in a real headless Factorio server and pass or fail it on measured throughput. Built to be driven by Claude Code, but usable by hand.

## Current Status

Two generators work in-game: `smelting_column` (all 3 samples confirmed) and `steel_column` (1 of 3). The headless evaluation harness, milestone 1 of the v2 optimizer, reproduces the confirmed in-game results. Milestone 2 (green circuits from beaconed electromagnetic plants, plus a solver and an optimiser) is planned in `docs/m2-plan.md` and not started. See `project-state.md` for detail and `session-summary.md` for history.

## Features

- Build a blueprint string from a JSON spec, by machine `count` or target `rate`
- Generators:
  - `smelting_column`: electric furnaces with lane balancing, so both output lanes fill
  - `steel_column`: ore to steel, with iron furnaces feeding steel furnaces by direct insertion
- Every draftsman warning (overlap, unknown entity) fails the build
- Static checks:
  - inserter pickup and drop targets
  - pole coverage and pole wiring
  - declared input and output ports
  - per-layout flow direction
- Headless evaluation (`evaluate`, `build --evaluate`): pastes the blueprint into a Factorio 2.0.77 headless server, feeds and powers it, and fails it if:
  - output is under 98% of target
  - any machine works under 95% of the time
  - any machine's output backs up
- Decode any blueprint string back to JSON

## Getting Started

Prerequisites: Python 3.10+, Factorio 2.0.x (with Space Age) installed. The headless harness runs on Linux.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/draftsman -p <Factorio install>/data update --no-mods   # load game data into draftsman
.venv/bin/blueprint-smith build examples/smelting_column.json      # string on stdout, notes on stderr
```

To judge blueprints in the headless harness:

```bash
.venv/bin/blueprint-smith install-server                 # downloads the free 2.0.77 headless server (~57 MB)
.venv/bin/blueprint-smith evaluate examples/steel_column.json
```

Use `factorio-draftsman<4`: version 4.x cannot load 2.0.x game data. Run tests with `.venv/bin/pytest -q`. The harness tests skip when the server isn't installed.

## Project Structure

- `src/blueprint_smith/` — pipeline, checks, ratio maths, CLI, `generators/` and `harness/`
- `tests/` — pytest suite, including a harness calibration suite
- `examples/` — sample specs
- `docs/` — `techniques.md` (learned mechanics and layout techniques) and the milestone plans
- `PROJECT_BRIEF.md` — confirmed scope (v1 and v2). `CLAUDE.md` — guidance for Claude Code

## Recent Changes

- **2026-10-11 (afternoon):**
  - Lane-balanced smelting column: all 3 samples pass in-game.
  - New `steel_column` generator.
  - Headless evaluation harness (v2 milestone 1).
  - Plan for milestone 2.
  - Spec validation fixes and a pole-reach fix.
- **2026-10-11** — First in-game test passed after a fix: the pipeline now wires power poles together, and a new `pole_network` check fails any unwired pole.
- **2026-09-29** — Scaffolded the package, CLI and pipeline, and added the `smelting_column` generator.

## Roadmap

v2 is a blueprint optimizer. You ask for something like "fill a turbo belt of green circuits", and it chooses machines, modules and beacons, lays out the block, and verifies it headlessly without an in-game test.
- Milestone 1, the harness, is done.
- Milestone 2 (solver, green-circuit generator, optimiser) is next.
- Learning from existing blueprints and freeform placement are stretch goals.
- Logistics and power & fluids generators are paused.

See `PROJECT_BRIEF.md`.

## License

MIT. See `LICENSE`.
