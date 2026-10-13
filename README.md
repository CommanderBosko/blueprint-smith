# Blueprint Smith

Generates importable Factorio 2.0 + Space Age blueprint strings from JSON specs. A Python CLI builds the layout with [factorio-draftsman](https://github.com/redruin1/factorio-draftsman), validates it, and encodes the string. It can also run the blueprint in a real headless Factorio server and pass or fail it on measured throughput. Built to be driven by Claude Code, but usable by hand.

## Current Status

Four generators work in-game:
- `smelting_column`: all 3 samples confirmed.
- `steel_column`: 1 of 3 samples.
- `circuit_block`: 240 green circuits/s.
- `plant_array`: 240.5 red circuits/s.

`blueprint-smith optimise` turns a request like "240 green circuits/s" or "240 red circuits/s" into the smallest blueprint that passes the headless harness. CI lints and runs the full suite, harness included, on every push and PR. The next milestone, M2c, generalises `plant_array` to any non-fluid machine and any in-block intermediate made from one item. Its scope is confirmed in `docs/m2c-brief.md`, and its plan comes next. For detail, see `project-state.md`; for history, `session-summary.md`.

## Features

- Build a blueprint string from a JSON spec, by machine `count` or target `rate`
- Generators:
  - `smelting_column`: electric furnaces with lane balancing, so both output lanes fill
  - `steel_column`: ore to steel, with iron furnaces feeding steel furnaces by direct insertion
  - `circuit_block`: green circuits from legendary electromagnetic plants. A cable plant feeds a circuit plant by direct insertion under shared beacons, filling both lanes of a stacked turbo belt (240/s). Copper comes in from the west (13×11) or the north (11×11).
  - `plant_array`: a beaconed array of product plants in two mirrored rows. Each is fed by direct insertion from an intermediate plant beside it. Built for red circuits (240/s on a stacked turbo belt).
- Every blueprint gets a display panel showing each input's item, and a lane balancer after each belt output
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

Use `factorio-draftsman<4`: version 4.x cannot load 2.0.x game data. Run tests with `.venv/bin/pytest -q`. The harness tests skip when the server isn't installed. CI runs `ruff check` and the non-harness tests on GitHub's runners. The full suite runs on a self-hosted runner, because factorio.com refuses the server download from GitHub's runners.

## Project Structure

- `src/blueprint_smith/` — pipeline, checks, ratio maths, CLI, `generators/` and `harness/`
- `tests/` — pytest suite, including harness calibration and measured-primitive suites
- `examples/` — sample specs
- `docs/` — `techniques.md` (learned mechanics and layout techniques) and the milestone plans
- `PROJECT_BRIEF.md` — confirmed scope (v1 and v2). `CLAUDE.md` — guidance for Claude Code

## Recent Changes

- **2026-10-13:**
  - M2c scoped: `plant_array` for any machine and any one-item intermediate (`docs/m2c-brief.md`). No code changes.
- **2026-10-12 (evening):**
  - The optimiser: `blueprint-smith optimise` (PR #7).
  - Red circuits on the generic `plant_array`, confirmed in-game at 240.5/s (PR #9).
  - Input display panels and output lane balancers on every blueprint (PR #9).
  - CI: lint, quick tests, and the full harness suite on a self-hosted runner, plus golden snapshots of every in-game-confirmed layout (PR #10).
- **2026-10-12:**
  - Milestone 2 pieces A–E, merged to `main` (PRs #2–#4).
  - Stacked-belt harness and the new machine bar.
  - `effects.py` solver and new generic checks.
  - Measured legendary stack-inserter rates.
  - `circuit_block`, confirmed in-game at 240/s.

## Roadmap

v2 is a blueprint optimizer. You ask for something like "fill a turbo belt of green circuits", and it chooses machines, modules and beacons, lays out the block, and verifies it headlessly without an in-game test.
- Milestone 1, the harness, is done.
- Milestone 2, the solver, checks, measured primitives, green-circuit block and optimiser (`blueprint-smith optimise`), is done. The optimiser's pick worked in-game.
- Milestone 2b, red circuits on a generic plant array, is done and confirmed in-game.
- Next: M2c, the plant array for any non-fluid machine and any one-item in-block intermediate (`docs/m2c-brief.md`). Automation science at 240/s is its done test.
- Fluids, fission, fusion and Gleba are deferred milestones, needed eventually.
- Learning from existing blueprints and freeform placement are stretch goals.
- The hand-written logistics and power & fluids generators are paused.

See `PROJECT_BRIEF.md`.

## License

MIT. See `LICENSE`.
