# Design Techniques

The catalog of everything learned about building good Factorio blueprints: the user's quality bar, game mechanics, and layout techniques. Each entry says how sure we are, where the code is, and which check enforces it.

**Read this before designing or changing any generator.** When the user teaches or corrects something (often with an in-game screenshot), add or update the entry in the same session.

Status labels:
- **Confirmed in-game (date):** seen working in the user's game.
- **Prototype data:** read from the game's data files, not yet seen in-game.
- **Inferred:** reasoned from other facts. Confirm in-game before relying on it heavily.

## Design checklist (for every generator)

Run through this when designing a new generator or changing an old one. It's how the entries below get combined.

1. **Size from the whole belt (P1).** Target rates use full-belt capacity (2 lanes, F11), not one lane. A column should be able to eat a full input belt.
2. **Every belt that inserters unload onto from one side needs lane balancing (T1).** Otherwise only the far lane fills (F1).
3. **Input belts need nothing extra.** Inserters take from both lanes (F2).
4. **Leave rows for poles (T2, T3).** The pipeline wires them (F6), and `pole_network` fails any pole it misses.
5. **Use facing-relative left/right for splitter priority (F5).** Never assume screen left.
6. **Enforce every technique in code.** Each technique a generator uses gets an invariant in its `check_flow` and a mutation test that breaks the layout on purpose and expects the build to fail.
7. **Share code, don't copy it.** When a second generator needs a technique, move it out of the first generator into a shared building block.
8. **Record the in-game result here.** After the user tests a blueprint, update the status of every entry it exercised.

## Principles (the user's quality bar)

### P1. Use whole belts
Both output lanes should fill, the full input belt should be eaten, and no machine should be blocked from unloading. "Runs at the specified rate" isn't enough. *Set by the user, 2026-10-11, after the copper and steel samples ran but wasted half of each belt.*

### P2. Two-tier acceptance
- **Guaranteed by the tooling:** a valid string that round-trips, no collisions, everything connected and powered, ratios computed.
- **Best-effort:** real throughput. Report it as `WARNING:` notes, never as failures, and never claim more than that. *From `PROJECT_BRIEF.md`.*

## Game mechanics

| # | Fact | Status |
|---|---|---|
| F1 | **Inserters drop onto the far lane** of a belt. | Confirmed in-game 2026-10-11 (copper 15/s: every plate on one lane) |
| F2 | **Inserters pick up from both lanes.** | Confirmed in-game 2026-10-11 (steel 3/s drained a full yellow belt of iron plates) |
| F3 | **Side-loading:** a belt feeding into the side of another puts everything onto the receiving belt's near lane. | Confirmed in-game 2026-10-11 (T1) |
| F4 | **Splitters keep lanes:** an item leaves on the same lane it entered. | Game rule, relied on by T1; not tested separately |
| F5 | **Splitter `output_priority` "left"/"right" is relative to the splitter's facing.** Facing south, `"right"` is the west output. | Confirmed in-game 2026-10-11 (priority arrows on the west half) |
| F6 | **A pasted blueprint keeps only the wires it carries.** Poles inside it don't auto-connect, even within reach. | Confirmed in-game 2026-10-11 (11 of 12 poles dead before the pipeline added wires) |
| F7 | An inserter's blueprint `direction` is the side it **picks up from**. | Prototype data; every in-game test so far flowed correctly |
| F8 | Directions: N=0, NE=2, E=4, S=8, W=12. | Prototype data |
| F9 | Underground belt `max_distance` is 5/7/9 tiles (total span, not the gap). | Prototype data |
| F10 | Medium electric pole: 7x7 supply area, wire reach 9. | Prototype data; poles 6 rows apart confirmed in-game 2026-10-11 |
| F11 | One belt lane carries `speed x 60 x 4` items/s: 7.5 yellow, 15 red, 22.5 blue, 30 turbo. A full belt carries double. | Prototype data (`ratios.belt_lane_capacity`) |
| F12 | Electric furnace: 3x3, crafting speed 2. Iron and copper plate take 3.2 s (0.625/s each); steel takes 16 s and 5 iron plates (0.125/s each). | Prototype data |

## Techniques

### T1. Lane balancing: priority splitter and side-load
**Solves:** machines that unload with inserters from one side fill only the belt's far lane (F1). Output is capped at half a belt, and once that lane is busy, the last machines can't unload.

**Applies when:** any belt that inserters drop onto from one side.

**Layout:** one module per 2 machines. In the smelting column (belts flow south, inserters drop east onto col 6):

```
col:    0   1   2 3 4   5   6
row 0   v   .   [ A ]   .   v
row 1   v   P   [ A ]   P   v
row 2   v   I   [ A ]   I   v
row 3   v   I   [ B ]   I   v
row 4   v   .   [ B ]   [SS]       splitter across cols 5-6, faces south, priority WEST
row 5   v   .   [ B ]   >   v      col 5 belt faces east and side-loads col 6

v belt south   > belt east   P medium pole   I inserter (moves west to east)   [SS] splitter
```

**Why it works:** inserters fill the far (east) lane. The splitter's output priority is on its west side, so plates leave west first, turn east, and side-load onto the near (west) lane (F3). They continue down the east lane only once the near lane is full. That keeps the far lane, where the inserters drop, as clear as possible, and both lanes end up full.

**Gotchas:**
- **Priority goes on the side opposite the inserters' drop lane.** It's easy to miss: the first version had no priority. *Corrected by the user, 2026-10-11.*
- Priority is facing-relative (F5): for a south-facing splitter, use `"right"`.
- Match the splitter tier to the belt (`_splitter_for`: same `speed`).
- Near a full belt, the last inserters may find few gaps in the far lane. This is best-effort (P2).

**Status:** confirmed in-game 2026-10-11 (copper 30/s on red belt, 48 furnaces). Shown to us by the user.

**Code:** `generators/smelting_column.py` (`SPLITTER_ROW`, `SIDELOAD_ROW`, `SPLITTER_PRIORITY`, `_splitter_for`).
**Enforced by:** `check_flow` (splitter faces south across cols 5-6 with west priority; an east-facing side-load belt sits under every splitter). Tests: `test_module_layout_balances_lanes`, `test_broken_lane_balancing_is_rejected`, `test_missing_sideload_belt_is_rejected`.

### T2. Paired inserters at the machine boundary
**Solves:** a 3-tile machine column has no spare rows for poles or the T1 splitter.

**Layout:** machine A unloads from its bottom row and machine B from its top row, so the 2 inserters on each side sit together (rows 2-3 above). That frees rows 1, 4 and 5 for the pole (T3) and the splitter and side-load (T1).

**Status:** confirmed in-game 2026-10-11. Shown to us by the user, as part of T1.
**Code:** `generators/smelting_column.py` (the A/B loop). **Enforced by:** `check_flow` (inserter pickup and drop columns) and `inserter_wiring`.

### T3. Pole ladder
**Solves:** powering a long column with as few poles as possible, and getting the wires into the blueprint (F6).

**Layout:** a medium pole in each inserter column (cols 1 and 5) on row 1 of every 2-machine module, which puts them 6 rows apart (reach 9, F10). The pipeline wires them axis-only into a ladder: one rung across each module, plus a rail down each side.

**Status:** confirmed in-game 2026-10-11.
**Code:** poles in `generators/smelting_column.py`; wiring in `pipeline.build` (`generate_power_connections(only_axis=True)`). **Enforced by:** `power_coverage` and `pole_network` in `checks.py`. Test: `test_column_poles_are_wired_as_a_ladder`.

## Open questions

- How close to a full belt does T1 really get at the bottom of a long column? Confirmed to come out correctly at 30/s; sustained throughput hasn't been measured.
- Do other machine shapes (assemblers with several inputs, fluids) need a different balancing module? Revisit with the next generator.
