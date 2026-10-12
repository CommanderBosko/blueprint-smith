# Blueprint Smith

Generates importable Factorio 2.0 + Space Age blueprint strings from JSON specs. A Python CLI builds the layout with [factorio-draftsman](https://github.com/redruin1/factorio-draftsman), validates it, and encodes the string. It can also run the blueprint in a real headless Factorio server and pass or fail it on measured throughput. Built to be driven by Claude Code, but usable by hand.

## Current Status

Three generators work in-game: `smelting_column` (all 3 samples confirmed), `steel_column` (1 of 3) and `circuit_block` (240 green circuits/s on a stacked turbo belt, confirmed). The headless harness agrees with every in-game result except one old layout. Milestone 2 has its solver, checks, measured inserter rates, generator and optimiser built: `blueprint-smith optimise` turns "240 green circuits/s" into an 11×11 block that passes the harness, waiting on an in-game spot-check. See `docs/m2-plan.md`, `project-state.md` for detail and `session-summary.md` for history.

## Features

- Build a blueprint string from a JSON spec, by machine `count` or target `rate`
- Generators:
  - `smelting_column`: electric furnaces with lane balancing, so both output lanes fill
  - `steel_column`: ore to steel, with iron furnaces feeding steel furnaces by direct insertion
  - `circuit_block`: green circuits from legendary electromagnetic plants. A cable plant feeds a circuit plant by direct insertion under shared beacons, filling both lanes of a stacked turbo belt (240/s). Copper comes in from the west (13×11) or the north (11×11).
- Solver (`effects.py`): quality, modules, beacons, research, power and demand, matching Factorio 2.0.77's rounding
- Every draftsman warning (overlap, unknown entity) fails the build
- Static checks:
  - inserter pickup and drop targets
  - pole coverage and pole wiring
  - module limits, beacon reach, underground pairing, survival-buildable entities
  - declared input and output ports
  - per-layout flow direction
- Headless evaluation (`evaluate`, `build --evaluate`; research defaults to what each blueprint type needs): pastes the blueprint into a Factorio 2.0.77 headless server, feeds it (stacked belts too) and powers it, and fails it if:
  - output is under 98% of target
  - a machine unloading onto a belt is blocked on output more than 5% of the time
  - any machine's output backs up

  Idle and unpowered time are reported as utilisation, not failed.
- Optimiser (`optimise`): give it a request such as `{"item": "electronic-circuit", "rate": 240}`. It tries every layout variant that the solver says could work, and returns the smallest one that passes the headless harness, using estimated power to break ties.
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
- `tests/` — pytest suite, including harness calibration and measured-primitive suites
- `examples/` — sample specs
- `docs/` — `techniques.md` (learned mechanics and layout techniques) and the milestone plans
- `PROJECT_BRIEF.md` — confirmed scope (v1 and v2). `CLAUDE.md` — guidance for Claude Code

## Recent Changes

- **2026-10-12:**
  - Milestone 2 pieces A–E, merged to `main` (PRs #2–#4).
  - Stacked-belt harness and the new machine bar.
  - `effects.py` solver and new generic checks.
  - Measured legendary stack-inserter rates.
  - `circuit_block`, confirmed in-game at 240/s.
- **2026-10-11 (afternoon):**
  - Lane-balanced smelting column: all 3 samples pass in-game.
  - New `steel_column` generator.
  - Headless evaluation harness (v2 milestone 1).
  - Plan for milestone 2.
  - Spec validation fixes and a pole-reach fix.
- **2026-10-11** — First in-game test passed after a fix: the pipeline now wires power poles together, and a new `pole_network` check fails any unwired pole.

## Roadmap

v2 is a blueprint optimizer. You ask for something like "fill a turbo belt of green circuits", and it chooses machines, modules and beacons, lays out the block, and verifies it headlessly without an in-game test.
- Milestone 1, the harness, is done.
- Milestone 2: the solver, checks, measured primitives, green-circuit generator and optimiser (`blueprint-smith optimise`) are built. Only the in-game spot-check of the optimiser's pick is left.
- Learning from existing blueprints and freeform placement are stretch goals.
- Logistics and power & fluids generators are paused.

See `PROJECT_BRIEF.md`.

## License

MIT. See `LICENSE`.
