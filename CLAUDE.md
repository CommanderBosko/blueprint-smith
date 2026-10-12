# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope First (Interview)

Use the `/interview` skill to pin down the real goal with the user before starting work whose scope or target is genuinely unclear — don't build against a guessed-at understanding of the request when guessing wrong would mean redoing the work. Skip it when the ask is already concrete (a single, already-diagnosed fix, a narrowly-scoped request) — a few blocking clarifying questions are enough there. When you do run it, surface the unknowns, confirm scope and constraints, and only proceed once the target is clear. Do this in tandem with the Verification Plan below: the interview establishes *what* we're building and how we'll know it's done, and the verification plan establishes *how we'll prove* it works.

## Verification Plan

Before you do any work, state how you'll verify it with the `/verify` skill — say up front how you'll confirm each part actually works before calling it done. Pick the checks that fit this project (build, test suite, linter, type-check, running the app, hitting the endpoint, reading the logs) and name the specific commands. Lay out the plan with the work, not after it.

## Parallelize with Sub-Agents

**This rule is your standing authorization to spawn sub-agents — you do not need to ask first.** Once scope and the verification plan are set, before starting any task with more than one independent part, stop and run a parallelization check. This is a required step, not an aspiration: ask "Can I split this into pieces that don't depend on each other's output?" If yes, spawn one sub-agent per piece in a single message and let them run concurrently.

Each spawned sub-agent must stay strictly inside the piece it was assigned — the exact file list or task boundary given in its prompt — and must not wander into a sibling agent's piece or the synthesis step reserved for you. A sub-agent that does more than its assigned slice (e.g. re-reading files assigned to another agent, or drawing conclusions across the whole task instead of just its piece) has gone out of scope, not "being extra helpful" — treat that as a bug to correct, the same way you would a wrong file edit.

Trigger parallelization whenever you hit any of these:
- About to research, search, or read across 2+ areas of the tree that don't depend on each other.
- About to scaffold or draft 2+ files whose *contents* don't reference each other.
- You catch yourself planning "do A, then B, then C" where B doesn't need A's result.

Reserve serial work for genuine dependencies — e.g. a new file and the line elsewhere that imports it are coupled, so keep them together. When the pieces are independent, default to fanning out breadth-first; state in your plan which pieces run in parallel and why.

## Use Existing Skills First

Before doing a task by hand, check whether an existing skill already covers it and invoke it instead of improvising. Skills encode the agreed, repeatable way to do a thing — prefer them over ad-hoc steps. If you find yourself doing the same multi-step task a second time and no skill exists, offer to create one.

## Ask via AskUserQuestion

When you need a decision, choice, or clarification from the user — not just information you can look up yourself — use the **AskUserQuestion** tool rather than asking in plain text. Phrase it as 2-4 concrete options (with a recommended one first); when the answer could be open-ended, the tool's built-in "Other" choice covers free text. This keeps answers structured, makes trade-offs explicit, and avoids an answer getting buried in prose. Reserve plain-text questions for genuinely open, generative prompts where no sensible options exist yet (e.g. "describe the project in your own words").

## Status

Scaffolded around draftsman 3.3.1 with four generators:
- `smelting_column`: all 3 samples confirmed in-game.
- `steel_column`: ore to steel by direct insertion; first sample confirmed in-game.
- `circuit_block`: M2's 240/s green circuit block. The west layout (the default) and the compact `copper: "north"` layout (11×11, the optimiser's pick) were both confirmed in-game on 2026-10-12. Following the user's in-game tweak, the stub now starts under its first inserter.

- `plant_array`: M2b's generic beaconed plant array, built for 240/s red circuits. Confirmed in-game 2026-10-12: 240.5/s with both lanes full, with the user's three resource cuts and their mid-row lane reset (T12) built in. With the reset, 1 output inserter a plant is enough (in-game 2026-10-12), and the optimiser picks it.
- Every blueprint gets input display panels (P3) and an output lane balancer (P4) from the pipeline. Both are confirmed in-game 2026-10-12.

`PROJECT_BRIEF.md` is the confirmed scope. Public GitHub repo: `CommanderBosko/blueprint-smith` (MIT), branch `main`.

**Now: the v2 blueprint optimizer** (`PROJECT_BRIEF.md`, v2 section, confirmed 2026-10-11).
- Milestone 1, the headless evaluation harness, is done.
- M2 pieces A–E (`docs/m2-plan.md`) are done and merged to `main` (PRs #2–#4, 2026-10-12).
- Piece F, the optimiser, is built on branch `v2-m2-f` (2026-10-12). `blueprint-smith optimise` picks the 11×11 north layout for 240/s, and that pick worked in-game on 2026-10-12. That completes M2's definition of done.
- Piece F is merged (PR #7). A follow-up on branch `verdict-growth-exemption` exempts machines that feed only other machines from the output-growth check (user, 2026-10-12).
- M2 is done.
- **Now: M2b, red circuits on a generic plant array** (`docs/red-circuits-plan.md`, scoped with the user 2026-10-12), on branch `v2-red-circuits`.
  - Pieces A–C are built: `blueprint-smith optimise` picks a 42×21 two-row block for 240/s (237.80/s in the harness, lanes 119/119).
  - The user built it in-game on 2026-10-12, cut resources in a couple of places and added an output balancer. Every block now gets input labels (P3) and an output lane balancer (P4) from the pipeline.
  - The generator now has the user's three changes, matching their copy entity for entity (238.09/s headless).
  - Piece D: the regenerated block ran at 240.5/s in-game with both lanes full (2026-10-12). **M2b is done.**
  - **Next:** commit and PR `v2-red-circuits` when the user asks, then pick the next milestone with them.
- M3 and M4 remain stretch goals.

Logistics and power & fluids generators are paused.

## Techniques Catalog

`docs/techniques.md` holds everything learned about making good blueprints: the user's quality bar (P), game mechanics (F) and layout techniques (T), each with its in-game status, code location and enforcing check.
- **Before designing or changing any generator,** read it and work through its design checklist. Combine the existing techniques rather than reinventing them.
- **When the user teaches or corrects a technique** (often with an in-game screenshot), add or update its entry in the same session. Record how it was confirmed, then enforce it with a check and a mutation test.
- **After each in-game test,** update the status of every entry the blueprint exercised.

## Commands

All via the venv (`.venv/bin/...`); the package is installed editable with `pip install -e ".[dev]"`.

- Tests: `.venv/bin/pytest -q` (about 70 s, because the `harness`-marked tests run the real headless server; they skip when it isn't installed). Quick run without them: `.venv/bin/pytest -q -m "not harness"`. Single test: `.venv/bin/pytest -q tests/test_smelting_column.py::test_reversed_inserters_are_rejected`
- Build a blueprint: `.venv/bin/blueprint-smith build examples/smelting_column.json` (`-` reads the spec from stdin, `-o FILE` writes the string). Notes go to stderr, the string to stdout. Exit codes: 0 ok, 1 failed validation, 2 bad spec.
- Evaluate in the headless harness: `.venv/bin/blueprint-smith evaluate SPEC` (verdict on stdout), or `build SPEC --evaluate` (prints the string only if the verdict passes). `--research` defaults to the research the spec's type registers (`circuit_block`: all; the furnace columns: none), and `--keep-run` keeps the run dir. Exit 3 means the harness couldn't run.
- Optimise: `.venv/bin/blueprint-smith optimise REQUEST`, where REQUEST is JSON such as `{"item": "electronic-circuit", "rate": 240}`. It prints the report to stderr and the winner's string to stdout; options are `-o FILE`, `--spec-out FILE`, `--jobs N`, `--max-runs N` and `--keep-run`. Exit 1 means no variant passed. 240/s takes about 17 s. `blueprint-smith install-server` downloads the 2.0.77 headless server into `~/.cache/blueprint-smith/`, and `$BPS_FACTORIO_SERVER` overrides its path.
- Decode: `.venv/bin/blueprint-smith decode STRING` or `@file`. List types: `.venv/bin/blueprint-smith types`.
- Confirmed layouts: `tests/test_confirmed.py` checks every in-game-confirmed block against its golden snapshot in `tests/fixtures/confirmed/`, entity for entity. After an intended layout change, re-pin with `BPS_UPDATE_SNAPSHOTS=1 .venv/bin/pytest -q tests/test_confirmed.py`, then re-test in-game (`docs/techniques.md` checklist item 8).
- Lint: `.venv/bin/ruff check`. It checks errors only (`E4,E7,E9,F` in `pyproject.toml`; `spike/` is excluded). `pyrightconfig.json` points editors at `.venv` and `src/`, but pyright isn't gated: most of its ~78 errors come from draftsman's types.
- CI (`.github/workflows/ci.yml`) runs on every push to `main` and every PR:
  - `lint` and `quick` (`pytest -m "not harness"`) run on GitHub-hosted runners.
  - `harness` runs the full suite on a self-hosted runner labelled `factorio` (the user's NixOS machine), because factorio.com answers 403 to the server download from GitHub's runners (2026-10-12). It never runs for a fork's PR.
  - `harness` sets `BPS_REQUIRE_HARNESS=1`. With that set, `tests/conftest.py` fails any skipped test, so a missing server can't turn the harness tests into silent skips. Set it locally to check the same thing.

## Code architecture (`src/blueprint_smith/`)

- `pipeline.build(spec)` is the single entry point: look up the generator by `spec["type"]`, build a draftsman `Blueprint`, then **turn every draftsman warning into a failure** (overlap, unknown entity, etc. only warn in draftsman) and run all checks. Any problem raises `BuildError`; a bad spec raises `SpecError`. Every block gets two ends from the pipeline:
  - A display panel showing each input's item, 2 tiles upstream of the input (P3, `labels`/`check_labels`). The panels are left out of `origin`, `optimise.footprint` and the harness's box, and the harness destroys them after pasting.
  - A lane balancer after each belt output (P4/T11, `balancers`/`check_balancers`), which moves the output port to its end.
  - The generator's own `checks=` and its ports are judged on its layout alone, before the ends are added.
- `generators/`: a generator is `spec -> (entities, notes, ports)`, registered with `@register(name, checks=(...), variants=..., research=...)`. `variants(request)` lists the candidate specs the optimiser may try, and `research` is what the harness runs the type with. A `Port` is a belt end the harness feeds or drains. `pipeline.build` makes port tiles relative to the blueprint's top-left and fails a port that isn't on an open belt end. Layout-specific checks go in `checks=` and are keyed by type name, so wrapping a generator in a test still applies them.
- `generators/columns.py`: building blocks shared by the furnace columns (spec options, `count`/`rate`, the 6-row A/B module).
- `generators/beaconed.py`: what the beaconed generators share: the standard meta's entities, the stacked turbo lane, spec counts, and `plant(recipe, quality, beacons)` rates from the solver.
- `generators/plant_array.py`: M2b's generic array.
  - Product plants are fed by direct insertion from intermediate plants beside them, in two mirrored rows around one shared beacon row.
  - A west front end splits each input belt between the rows and merges the two near items one per lane (T8). The cable plants reach their copper with long-handed inserters (T10).
  - An east merge brings both rows onto one belt (T9).
  - `sizing` holds the link math, including the free-slot output model (T7).
- `generators/circuit_block.py`: the M2 green circuit block. Its spec options (copper side, beacons, inserters per link) are what the optimiser varies. `sizing` holds the link math that both the notes and `variants` use.
- `checks.py`: generic checks for every blueprint. These can't tell a reversed inserter from a correct one; direction/flow correctness is each generator's own `check_flow`.
  - Inserter pickup and drop positions hit an entity.
  - Electric consumers are inside a pole's supply area.
  - Module limits, beacon reach, underground pairing, and survival-buildable entities.
  - `beacon_targets(bp)` maps each machine to the beacons reaching it.
- `ratios.py`: machine counts and belt lane capacity from prototype data, at base crafting speed (the M1 generators use it).
- `effects.py`: the M2 solver.
  - Quality, modules, beacons, research, power and demand, with 2.0.77's whole-percent rounding (F19).
  - `entity_rates(machine, beacons=checks.beacon_targets(bp)[machine])`.
  - Measured inserter rates in `LEGENDARY_STACK_INSERTER`.
- Notes vs. errors: statically, real throughput is best-effort, so it appears as `WARNING:` notes (for example a column whose output is more than its plate belt carries), never as failures. The headless harness (amended P2) turns throughput into a hard pass/fail.
- `optimise.py`: M2 piece F.
  - Builds every variant serially.
  - Ranks them by footprint (`footprint`: bounding-box tiles), then by `power_estimate`, a tie-break only, since the harness doesn't measure power draw.
  - Runs the harness best-first in parallel batches, and stops at the first batch that holds a pass.
- `harness/`: the headless evaluation harness (technique H1 in `docs/techniques.md`).
  - `mod/control.lua` is the in-game side: it pastes, feeds, powers and measures, then writes a JSON result.
  - `runner.py` runs `--create` then `--benchmark` in a temp dir and parses the result. `verdict.py` judges it; its output-growth bar allows for the biggest hand unloading each machine (`growth_max`).
  - `evaluate.py` picks the warmup and window and ties them together.
  - Each run takes about 6 s, and runs can go in parallel. `pipeline.build` records warnings process-wide, so build serially and only run the harness in threads.

Conventions worth knowing: an inserter's blueprint `direction` is the side it **picks up from**. Entities are placed by `tile_position` (top-left tile). Build entities with `draftsman.entity.new_entity(name, ...)`, since there is no per-entity class such as `ElectricFurnace`.

## What this is

Claude Code acts as a Factorio blueprint crafter. Claude writes a JSON spec. A Python CLI turns it into entities, validates them, and encodes an importable blueprint string. The user imports it in-game and reports failures back. Read `PROJECT_BRIEF.md` before changing scope.

## Planned architecture (from the brief)

- **Encode/decode:** blueprint strings are a version byte + base64(zlib(JSON)). Every change to this must keep the decode→encode round-trip test against real blueprints passing. `~/.factorio/blueprint-storage-2.dat` is a possible source of samples.
- **Prototype data loader:** entity sizes and recipes live in Lua and need the data stage to run, so plain JSON on disk isn't enough. Options: `factorio --dump-data` (writes `data-raw-dump.json`) or parsing the Lua. Keep the loader mod-aware, but v1 is tested against vanilla + Space Age only.
- **Generators:** production lines come from parametric generators/templates, not freeform placement. Staging is production lines first, then logistics, then power & fluids.
- **Validator:** the tooling guarantees a valid string, round-trip, no collisions, connectivity, and computed ratios. Real throughput (belt merging, fluid flow, inserter timing) is best-effort only. Don't claim more than that to the user.
- **Failure loop:** the CLI returns a failure report and Claude fixes the spec and re-runs.

## Environment facts

- Factorio 2.0.77 with Space Age, at `~/.local/share/Steam/steamapps/common/Factorio` (data in `.../data`). Not on `PATH`.
- The Steam install is the **Windows build under Proton** (`bin/x64/factorio.exe`, Proton prefix `compatdata/427520`). There is no native Linux binary, so headless runs need the Linux headless server. The offline Lua API docs for 2.0.77 are in `.../Factorio/doc-html/`.
- User dir `~/.factorio` has 65 mods in `mods/`; `mods/mod-list.json` lists which are enabled. The mod list is already on disk, so no screenshot is needed.
- Python is the chosen language. Venv at `.venv` (Python 3.14) with `factorio-draftsman<4`. Do NOT upgrade to draftsman 4.x: it can't load 2.0.77 data. Regenerate its data with `.venv/bin/draftsman -p ~/.local/share/Steam/steamapps/common/Factorio/data update --no-mods`.
- Draftsman API gotchas: import with `Blueprint.from_string(s)` (`Blueprint(s)` sets the label); validation only emits warnings, so the CLI must escalate `OverlappingObjectsWarning`/`UnknownEntityWarning` to failures.
- Verified: directions N=0 E=4 S=8 W=12 (NE=2); underground `max_distance` is 5/7/9 total. `spike/` holds the throwaway feasibility scripts.

## Out of scope for v1

Base/city-block planning, live game integration (RCON, the user's game or saves), GUI/web front end, Space Age planet/platform builds, and tested mod support (stretch goal). v2 allows in-game scripting for the headless harness only, and replaces "no belt-perfect optimization" with the harness pass bar.
