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
- Layouts come from parametric generators/templates, not freeform placement.

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
- **Best-effort:** real throughput (belt merging, fluid flow and inserter timing aren't statically provable).
- **Done:** about 3 sample specs per shipped type import into the game without error and run as specified. The user confirms in-game and reports failures.

## Out of scope
- City-block/base planning.
- Live game integration (RCON, in-game scripting).
- GUI/web front end.
- Belt-perfect optimization.
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
