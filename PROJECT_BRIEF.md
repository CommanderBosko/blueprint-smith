# Project Brief: Blueprint Smith

## Goal
Claude Code generates importable Factorio 2.0 + Space Age blueprint strings from natural-language or exact-parameter specs. A Python CLI builds, validates and encodes them.

## Problem
Hand-building layouts is slow. Claude can't reliably write blueprint strings (base64+zlib JSON) unaided: overlaps, rotations and belt connectivity are easy to get wrong.

## User
Just the author.

## Interface
- Claude writes a JSON spec.
- The Python CLI generates entities, validates, and encodes the string.
- The CLI returns a failure report that Claude fixes and re-runs.
- Layouts come from parametric generators/templates, not freeform placement. (Freeform placement is a v2 stretch goal; see below.)

## v1 staging
1. **Production lines** (first milestone).
2. Logistics.
3. Power & fluids.

## Must-haves
- Encode/decode blueprint strings, with a decode→encode round-trip test against real blueprints (`~/.factorio/blueprint-storage-2.dat` is a possible source).
- Load entity/recipe data from the local install (2.0.77 + Space Age).
- Static validation: overlaps, rotations, belt/inserter connectivity, ratios computed.
- Accept loose and exact specs.

## Acceptance (two-tier)
- **Guaranteed by tooling:** valid string, round-trips, no collisions, connected, ratios computed.
- **Best-effort:** real throughput (belt merging, fluid flow and inserter timing aren't statically provable). *v2:* a headless harness run turns throughput into a hard pass/fail (see below).
- **Done:** about 3 sample specs per shipped type import into the game without error and run as specified. The user confirms in-game and reports failures.

## Out of scope
- City-block/base planning.
- Live game integration (RCON, connecting to the user's game or saves). *v2:* in-game scripting is allowed for the headless evaluation harness only.
- GUI/web front end.
- Belt-perfect optimization. *v2:* replaced by the harness bar below.
- Space Age planet/platform builds until the core types work.
- Mods are a **stretch goal**: the loader should be mod-aware, but v1 done covers vanilla + Space Age only.

## Environment facts
- Game: `~/.local/share/Steam/steamapps/common/Factorio` (data at `.../data`).
- User dir: `~/.factorio` (65 mods in `mods/`, mostly zips; `mod-list.json` lists the enabled ones).
- Version: Factorio 2.0.77, Space Age enabled.

## Open risks
- Prototype data lives in Lua and needs the data stage to run, so it isn't plain JSON. Options: run `factorio --dump-data` (writes `data-raw-dump.json`) or parse the Lua.
- Mod data variety.
- Spatial correctness of generated layouts.

---

# v2: Blueprint Optimizer

*Confirmed by the user 2026-10-11, after an interview and an independent review. Amends the v1 sections above where marked. This is the next work; the logistics and power & fluids generators are paused.*

## Goal
The user asks in plain words, e.g. *"fill a turbo belt of green circuits"*. Claude writes the spec. The system chooses the machines, modules and beacons, lays out the blueprint, and verifies it in a headless run without the user importing it. Throughput is a hard bar. Among the layouts that pass, it minimises footprint: bounding-box tiles, including the input and output belts, with power use as the tiebreak.

## Problem
Every production line needs a hand-written generator, every blueprint needs the user's in-game test before it can be trusted, and `ratios.py` ignores modules and beacons.

## Method
Better blueprints are the goal; ML is optional. Module and beacon counts come from solver math. Layout uses whatever search or learned model works best. A trained model is used only where it beats search or solver methods.

## Must-haves
- **M1: Evaluator.**
  - A headless harness (vanilla + Space Age) pastes the blueprint, feeds each declared input port at its belt's rate, powers it from an infinite source, and measures a steady-state window. *Amended 2026-10-11 after the spike: the window is max(60 s, 10 × the slowest craft cycle), and the warmup is max(2 min, 3 × belt transit, 10 × craft cycle), because furnaces fed together craft in step.*
  - It reports four measures: output items/s against the target, fill of both output lanes, each machine's share of working ticks, and power satisfaction.
  - Generators declare their input and output ports.
- **Amended P2 (`docs/techniques.md`):** a harness run fails the build if output is below 98% of the target or any machine works less than 95% of ticks. Static-only builds keep their `WARNING:` notes. *Two more failures were added 2026-10-11 to catch jams that a machine's output buffer hides (F15): a machine whose output backs up by more than 3 items over the window, and crafted output that doesn't reach the output port (under 80% delivered).*
- **M2: Solver and green circuits.**
  - Module and beacon math with the standard meta: productivity modules in machines, speed modules in beacons.
  - Defaults are the best available machine (the electromagnetic plant for circuits) and legendary machines, modules and beacons. A request can override any of these.
  - A beaconed green-circuit layout, plus an optimiser over generator variants scored by the harness.
  - *Decided 2026-10-11 when M2 started:*
    - Iron and copper plates come in on belts, and the block makes its own copper cable.
    - "Fill a turbo belt" means **stacked: 240/s** (Space Age belt stacking).
    - **Everything is researched** by default; a request can override levels. `ratios.py` must model research bonuses, and M2's harness runs use `--research all`.
    - **Machine bar:** a machine fails only if it is blocked on output for more than 5% of the window, or its output buffer grows. Idle time from over-capacity is reported, not failed, because beacons come in whole steps and one machine can't be sized exactly. This replaces "every machine working at least 95%". *Amended 2026-10-12:* unpowered time isn't judged (power is never short in the user's save), and a machine that unloads only into other machines isn't judged on blocking, because under direct insertion spare capacity shows as blocked rather than idle. Plan: `docs/m2-plan.md`.
- **Requests** are single blocks with their inputs on belts at the edge. If a request is ambiguous, Claude asks the user before building.
- **M2b: red circuits on a generic plant array** (*decided by the user 2026-10-12, after M2*). Plan: `docs/red-circuits-plan.md`.
  - "Fill a turbo belt of red circuits": 240/s stacked, the same bar and defaults as M2.
  - Green circuits, plastic and copper plates come in on belts, and the block makes its own copper cable.
  - The generator is generic: a beaconed array of plants parametrised by recipe, with an optional in-block intermediate (cable) handed over by direct insertion. Red circuits are its first recipe and its done test.
  - Layout approved by the user 2026-10-12: two mirrored rows around one shared beacon row. Each row has a green|plastic belt, and a copper belt one row further out that the cable plants reach with long-handed inserters. The two output belts merge into one.
- **M2c: the plant array for any machine and any one-item intermediate** (*scoped with the user 2026-10-12/13, after M2b; independently reviewed*). Full brief: `docs/m2c-brief.md`.
  - `{"item", "rate"}` is enough. The optimiser tries each capable electric machine (assembler 1/2/3, EM plant, electric furnace, foundry for belts) and every one-item ingredient that can be made in-block, smelted ones included, and footprint picks. A request may override the machine, the intermediate and quality.
  - Stone and steel furnaces only on request, with fuel on a belt. P and K may be different machines and sizes. 0 to 2 near items. Speed-3 in machines whose recipe refuses productivity.
  - Layout stays P > K < P. It also delivers a comparison report (K use, and an estimate for one K feeding many) and a readiness table for the deferred milestones.
  - Deferred, each a required future milestone: fluids, fission, fusion, Gleba, intermediates made from 2+ items and chains of them, arrays with no intermediate, 3+ near items, and a second layout.

## Nice-to-haves / stretch
- The harness loads the user's enabled mods, if that isn't too difficult. Vanilla + Space Age is the must.
- A Python simulator or static score, only if the harness is too slow for search.
- **M3** (learning from existing blueprints, e.g. `blueprint-storage-2.dat`) and **M4** (freeform placement) stay stretch goals until each has a defined output and done test.

## Out of scope
- RCON or any connection to the user's live game or saves.
- City-block planning, and chain-to-raw requests until logistics exists.
- Gleba and other planet builds (bioflux, spoilage, nutrients) until the Nauvis types work. *Amended 2026-10-13 (M2c):* Gleba, fluids, fission and fusion are deferred, not dropped: each is a required future milestone.
- New hand-written logistics or power & fluids generators (paused).
- ML for its own sake.

## Constraints
- Python, using the existing pipeline. draftsman stays below version 4.
- Factorio 2.0.77 + Space Age. The Steam install is the Windows build under Proton (`bin/x64/factorio.exe`), so the harness needs the native Linux headless server, pinned to the same version.
- Hardware: 16 cores, 62 GB RAM, RTX 3070 (8 GB).
- No deadline.

## Definition of done
- **M1:**
  - The harness runs unattended and the time per run is measured.
  - It reproduces three confirmed results: iron 15/s with both lanes full, steel 3/s from plates, and steel 3/s from ore with every furnace working.
  - It reproduces copper 30/s, after the user re-checks in-game that the bottom furnaces aren't blocked.
  - It catches the three confirmed failures:
    - the pre-T1 copper layout filling one lane (git `f1d113a`)
    - the pre-T1 steel layout's last furnaces blocked on output (git `f1d113a`, `examples/smelting_column_steel.json`)
    - unwired poles (predates git; recreate by skipping the wiring step)
- **M2 (the end goal):**
  - "Fill a turbo belt of green circuits" produces a beaconed, standard-meta, electromagnetic-plant blueprint that passes the harness: at least 98% of 240/s (a stacked turbo belt), no machine blocked on output, with everything researched.
  - The optimiser returns the smallest passing variant.
  - The user's spot-checks of the first few layouts it approves agree with the harness.
- **M2b:**
  - `blueprint-smith optimise` on `{"item": "advanced-circuit", "rate": 240}` returns a plant-array blueprint that passes the harness: at least 98% of 240/s, both output lanes full, no machine failing the machine bar, with everything researched.
  - The user's in-game spot-check of the pick agrees with the harness.
- **M2c** (details in `docs/m2c-brief.md`):
  - `blueprint-smith optimise` on `{"item": "automation-science-pack", "rate": 240}` passes the harness under M2b's bar, with whichever intermediate wins, and the user's in-game check of the pick agrees.
  - Seven proof requests (assembler 1 and 2, electric furnace, a mixed assembler/furnace row, the foundry, and stone and steel furnaces) each pass the harness at a rate needing 4+ product machines a row.
  - Every in-scope recipe builds and passes the static checks.
  - The existing confirmed fixtures, the red pick and the green pick (`circuit_block`'s 11×11) don't change.
  - The user decides on the second layout from the comparison report, and signs off the readiness table.

## Risks
- **Running the server:** it needs its own write directory, and an unattended run needs a start-run-exit flow.
- **Run time:** time per harness run is unknown.
- **Quality data:** draftsman 3.3.1 may not carry quality stats or encode module requests with quality.
- **2.0 beacon rules:** 1/√n diminishing returns and the recipe productivity cap must be modelled correctly.
- **Mods gap:** the harness runs vanilla, and every past in-game confirmation was in the user's modded game (67 enabled mods, including `long_stack_inserter` and `squeak-through-2`).
- **Calibration:** the set is all furnaces. There is no ground truth for assemblers or beacons until the M2 spot-checks.
