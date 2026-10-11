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

Scaffolded around draftsman 3.3.1 with one generator (`smelting_column`). `PROJECT_BRIEF.md` is the confirmed scope. Public GitHub repo: `CommanderBosko/blueprint-smith` (MIT), branch `main`. Logistics and power & fluids generators are not started.

## Commands

All via the venv (`.venv/bin/...`); the package is installed editable with `pip install -e ".[dev]"`.

- Tests: `.venv/bin/pytest -q`. Single test: `.venv/bin/pytest -q tests/test_smelting_column.py::test_reversed_inserters_are_rejected`
- Build a blueprint: `.venv/bin/blueprint-smith build examples/smelting_column.json` (`-` reads the spec from stdin, `-o FILE` writes the string). Notes go to stderr, the string to stdout. Exit codes: 0 ok, 1 failed validation, 2 bad spec.
- Decode: `.venv/bin/blueprint-smith decode STRING` or `@file`. List types: `.venv/bin/blueprint-smith types`.
- No linter is configured. `pyrightconfig.json` points editors at `.venv` and `src/`.

## Code architecture (`src/blueprint_smith/`)

- `pipeline.build(spec)` is the single entry point: look up the generator by `spec["type"]`, build a draftsman `Blueprint`, then **turn every draftsman warning into a failure** (overlap, unknown entity, etc. only warn in draftsman) and run all checks. Any problem raises `BuildError`; a bad spec raises `SpecError`.
- `generators/`: a generator is `spec -> (entities, notes)`, registered with `@register(name, checks=(...))`. Layout-specific checks go in `checks=` and are keyed by type name, so wrapping a generator in a test still applies them.
- `checks.py`: generic checks for every blueprint (inserter pickup/drop hit an entity, electric consumers are inside a pole's supply area). These can't tell a reversed inserter from a correct one. Direction/flow correctness is each generator's own `check_flow`.
- `ratios.py`: machine counts and belt lane capacity from prototype data. Base crafting speed only, no modules or beacons yet.
- Notes vs. errors: real throughput is best-effort, so it appears as `WARNING:` notes (for example the single-lane plate belt limit of 7.5/s on yellow belt), never as failures.

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
- User dir `~/.factorio` has 65 mods in `mods/`; `mods/mod-list.json` lists which are enabled. The mod list is already on disk, so no screenshot is needed.
- Python is the chosen language. Venv at `.venv` (Python 3.14) with `factorio-draftsman<4`. Do NOT upgrade to draftsman 4.x: it can't load 2.0.77 data. Regenerate its data with `.venv/bin/draftsman -p ~/.local/share/Steam/steamapps/common/Factorio/data update --no-mods`.
- Draftsman API gotchas: import with `Blueprint.from_string(s)` (`Blueprint(s)` sets the label); validation only emits warnings, so the CLI must escalate `OverlappingObjectsWarning`/`UnknownEntityWarning` to failures.
- Verified: directions N=0 E=4 S=8 W=12 (NE=2); underground `max_distance` is 5/7/9 total. `spike/` holds the throwaway feasibility scripts.

## Out of scope for v1

Base/city-block planning, live game integration (RCON), GUI/web front end, belt-perfect optimization, Space Age planet/platform builds, and tested mod support (stretch goal).
