# Design Techniques

The catalog of everything learned about building good Factorio blueprints: the user's quality bar, game mechanics, and layout techniques. Each entry says how sure we are, where the code is, and which check enforces it.

**Read this before designing or changing any generator.** When the user teaches or corrects something (often with an in-game screenshot), add or update the entry in the same session.

Status labels:
- **Confirmed in-game (date):** seen working in the user's game.
- **Prototype data:** read from the game's data files, not yet seen in-game.
- **Inferred:** reasoned from other facts. Confirm in-game before relying on it heavily.
- **Headless 2.0.77 (date):** measured in the headless harness (H1), not yet seen in the user's game.

## Design checklist (for every generator)

Run through this when designing a new generator or changing an old one. It's how the entries below get combined.

1. **Size from the whole belt (P1).** Target rates use full-belt capacity (2 lanes, F11), not one lane. A column should be able to eat a full input belt.
2. **Every belt that inserters unload onto from one side needs lane balancing (T1) if its output can exceed one lane.** Otherwise only the far lane fills (F1). Skip T1 when the output can never fill one lane (the steel column's output is a fifth of its input). When one machine's edges are all there is to unload from, as in the circuit block, use a side-load stub instead (T5). Even when the output fits one lane, reset the lane halfway once inserters fill it close to full (T12), or the last machines wait for gaps.
3. **Input belts need nothing extra.** Inserters take from both lanes (F2).
4. **Leave rows for poles (T2, T3).** The pipeline wires them (F6), and `pole_network` fails any pole it misses. Supply reach is measured from the pole's centre (F10), so a medium pole covers 3 tiles either side of its own column.
5. **Use facing-relative left/right for splitter priority (F5).** Never assume screen left.
6. **Enforce every technique in code.** Each technique a generator uses gets an invariant in its `check_flow` and a mutation test that breaks the layout on purpose and expects the build to fail.
7. **Share code, don't copy it.** When a second generator needs a technique, move it out of the first generator into a shared building block.
8. **Record the in-game result here.** After the user tests a blueprint, update the status of every entry it exercised. Also pin the tested layout in `tests/fixtures/confirmed/`. For a block already pinned, run `BPS_UPDATE_SNAPSHOTS=1 .venv/bin/pytest -q tests/test_confirmed.py` and update the fixture's `confirmed` line. For a new block, first add a fixture with its `spec`, a `confirmed` line and `"entities": []`. A change that moves a pinned layout fails `test_confirmed` until it's re-pinned, which is the cue for another in-game test.
9. **Size beaconed machines with the solver, not by hand.** Count each machine's beacons with `checks.beacon_targets` (F24) and pass them to `effects.entity_rates` (F19–F21). The generic checks already enforce module limits, underground pairing and survival-buildable entities (F25–F27).
10. **Leave 2 free tiles upstream of every input (P3).** The pipeline puts the input's label on the second; a layout that fills it fails on the overlap.
11. **Leave room after every belt output (P4, T11).** The pipeline adds a lane balancer 3 tiles long and 3 wide, centred on the output's line. Don't balance the output inside the generator too.
12. **Spend undergrounds and belts sparingly** (the user's red block copy, 2026-10-12):
    - When one belt crosses several, hop that one under all of them with one pair, rather than each of them under it.
    - Merge two items onto one belt where they first sit side by side (T8).
    - Merge two outputs by side-loading from both sides, not by passing one under the other (T9).

## Principles (the user's quality bar)

### P1. Use whole belts
Both output lanes should fill, the full input belt should be eaten, and no machine should be blocked from unloading. "Runs at the specified rate" isn't enough. *Set by the user, 2026-10-11, after the copper and steel samples ran but wasted half of each belt.*

### P2. Two-tier acceptance
- **Guaranteed by the tooling:** a valid string that round-trips, no collisions, everything connected and powered, ratios computed.
- **Best-effort:** real throughput. Report it as `WARNING:` notes, never as failures, and never claim more than that. *From `PROJECT_BRIEF.md`.*
- **Amended for v2, in effect since 2026-10-11 (H1):** a headless harness run (`blueprint-smith evaluate`, `build --evaluate`) is a hard pass/fail. Builds checked only statically keep the `WARNING:` notes. A run fails if:
  - the crafted output is below 98% of the target (the sink rate when no machine makes the item);
  - any machine is blocked on output (`full_output`, `waiting_for_space_in_destination`, `full_burnt_result_output`) for more than 5% of the window;
  - any machine's output backs up: more than 3 items gained, or more than the biggest hand among the inserters unloading it (amended by the user 2026-10-12: a legendary stack inserter's 16-item hand made a flowing red plant read 4–7 items of growth that didn't build over 6× the window);
  - or less than 80% of the crafted output reaches the output port.

  Idle time isn't failed: beacons come in whole steps, so an honest design runs some machines under capacity. Each machine kind's utilisation (min and mean share working) is reported instead, and the output bar catches a starved line. Unpowered time isn't judged either, only reported: power is never short in the user's save (user, 2026-10-12). A machine that unloads **only into other machines** isn't judged on blocking or on output growth (growth added by the user 2026-10-12, after it falsely failed 2 of 8 optimiser variants: the buffer fills to a cap and waits): under direct insertion its consumer sets the pace, so spare capacity shows as `full_output` instead of idle (user, 2026-10-12, after the circuit block's cable plant read 55% blocked while the block delivered 240/s). *The M2 machine bar was decided by the user and implemented 2026-10-11. It replaced "every machine working at least 95%".*

### P3. Label every input
Each input gets a display panel showing its item, in line with the belt, 2 tiles upstream of its first belt tile. The tile between stays free, so a supply belt can come in from the side and turn into the input. That way the user can tell at a glance which belt carries what.
- **Status:** set by the user 2026-10-12 with a screenshot of their own build (plastic, green circuits and copper panels over three input belts, with one free tile between each panel and its belt). First applied to the red circuit block (M2b). **Confirmed in-game 2026-10-12** in the generated red block (the user: "The display panels are placed perfectly").
- **Code:** `pipeline.labels` adds the panels to every generator's blueprint, so generators don't place them. Outputs aren't labelled.
- **The panels aren't part of the block.** `pipeline.origin` (port tiles), `optimise.footprint` and the harness's box all leave them out. The harness destroys them after pasting, so the loaders of unstacked inputs fit where the panel stood.
- **Enforced by:** `pipeline.check_labels` (every input has a panel showing its item at that tile), with mutation tests in `tests/test_ports.py` (no panel, wrong item, one tile too close).

### P4. Balance every belt output's lanes
Every output that leaves on a belt ends in a lane balancer (T11), so the belt leaves with the same amount on both lanes whatever the block upstream did.
- **Status:** set by the user 2026-10-12 ("any output using a belt should have a balancer at the end"), with a screenshot of one they added to the red circuit block's output in-game. **Confirmed in-game as generated, 2026-10-12** (the red block: "The balancer works", both output lanes full).
- **Code:** `pipeline.balancers` adds one after every generator's output and moves the output port to its end. Generators don't place it, and their own `check_flow` judges their layout before it's added.
- **Enforced by:** `pipeline.check_balancers` (the whole balancer, of the output belt's tier, ends at every output port). Tests in `tests/test_ports.py`: every example and the red block end in one, plus mutation tests (no splitter, the straight half running on, the curved half missing its turn back in).

## Game mechanics

| # | Fact | Status |
|---|---|---|
| F1 | **Inserters drop onto the far lane** of a belt. | Confirmed in-game 2026-10-11 (copper 15/s: every plate on one lane); again in the circuit block, 2026-10-12 (the east inserters fill the east lane); again in the optimiser's circuit block (north copper), 2026-10-12 (east lane full) |
| F2 | **Inserters pick up from both lanes.** | Confirmed in-game 2026-10-11 (steel 3/s drained a full yellow belt of iron plates, on both the old and lane-balanced layouts) |
| F3 | **Side-loading:** a belt feeding into the side of another puts everything onto the receiving belt's near lane. | Confirmed in-game 2026-10-11 (T1: copper 30/s, iron 15/s, steel 3/s); again in the circuit block, 2026-10-12 (T5: the stub fills the west lane); again in the optimiser's circuit block (north copper), 2026-10-12 (west lane full from the shortened stub); again in the red circuit block, 2026-10-12 (T8's mixed belts, T9's merge and the lane balancer: both output lanes full) |
| F4 | **Splitters keep lanes:** an item leaves on the same lane it entered. | Game rule, relied on by T1; not tested separately |
| F5 | **Splitter `output_priority` "left"/"right" is relative to the splitter's facing.** Facing south, `"right"` is the west output. | Confirmed in-game 2026-10-11 (priority arrows on the west half) |
| F6 | **A pasted blueprint keeps only the wires it carries.** Poles inside it don't auto-connect, even within reach. | Confirmed in-game 2026-10-11 (11 of 12 poles dead before the pipeline added wires); again in the red circuit block, 2026-10-12 (all 24 pipeline-wired poles: every plant ran) |
| F7 | An inserter's blueprint `direction` is the side it **picks up from**. | Prototype data; every in-game test so far flowed correctly (pick-up sides west and south). North first used by the circuit block's north copper inserter (T6): headless 2.0.77 2026-10-12; confirmed in-game 2026-10-12 (the north-picking copper inserter fed the cable plant from the belt above it) |
| F8 | Directions: N=0, NE=2, E=4, S=8, W=12. | Prototype data |
| F9 | Underground belt `max_distance` is 5/7/9/11 tiles for yellow/red/blue/turbo, from entrance to exit (total span, not the gap). | Prototype data; headless 2.0.77, 2026-10-11 (yellow pairs at 5 not 6, turbo at 11 not 12); turbo pairs spanning 5 and 6 tiles confirmed in-game in the red circuit block, 2026-10-12 (the copper hop under both near belts, the risers under the beacon row) |
| F10 | Medium electric pole: 7x7 supply area, wire reach 9. The supply area spans `supply_area_distance` either side of the pole's **centre**, not its edge (small 5x5, medium 7x7, big 4x4, substation 18x18). | Prototype data; poles 6 rows apart confirmed in-game 2026-10-11. `power_coverage` measured from the edge until 2026-10-11, found by the steel column's mutation test |
| F11 | One belt lane carries `speed x 60 x 4` items/s: 7.5 yellow, 15 red, 22.5 blue, 30 turbo. A full belt carries double. | Prototype data (`ratios.belt_lane_capacity`); full yellow belt (15/s) confirmed in-game 2026-10-11 (iron, both lanes full) |
| F12 | Electric furnace: 3x3, crafting speed 2. Iron and copper plate take 3.2 s (0.625/s each); steel takes 16 s and 5 iron plates (0.125/s each). So one iron furnace makes exactly what one steel furnace eats (0.625 plates/s), at any crafting speed. | Prototype data; iron confirmed in-game 2026-10-11 (24 furnaces filled both lanes of a yellow belt); 1:1 pairing confirmed in-game 2026-10-11 (steel column, every furnace running) |
| F13 | **Furnaces pick their recipe from their input:** ore makes plates, iron plates make steel. Blueprints don't set a furnace recipe. | Confirmed in-game 2026-10-11 (steel column: ore-fed furnaces made plates, plate-fed furnaces made steel) |
| F14 | **Research changes throughput.** Space Age's steel-plate productivity research adds +10% steel at level 1, and inserter capacity research raises hand size. `ratios.py` assumes no research, so the harness defaults to none (`--research all` researches everything). `effects.py` models research for M2 (F23). | Headless 2.0.77, 2026-10-11 (steel furnaces made 11 crafts in 80 s with all research, 10 without) |
| F15 | **A machine buffers a stack of output** (100 plates is about 160 s of an iron furnace, 800 s of a steel one). A furnace whose output is blocked keeps crafting into that buffer and still reads "working", so a jam can hide for minutes. Watch the buffer grow instead. | Headless 2.0.77, 2026-10-11 (pre-T1 copper asked for 30/s: every furnace "working" while the bottom 24 gained 38 plates each) |
| F16 | **A script-revived blueprint keeps** splitter `output_priority` and the copper wires it carries, and fulfilling module requests by script keeps their quality. | Headless 2.0.77, 2026-10-11 |
| F17 | **A script can stack items on a belt without a loader or research:** `insert_at_back({name, count=4}, 4)` once per lane per tick holds a turbo belt at 240/s (120 per lane). A turbo loader drains a stacked belt at the full 240/s, so only the feed side needs the script. | Headless 2.0.77, 2026-10-11 (`tests/test_harness_m2.py`) |
| F18 | **Statuses:** a starved assembler reads `item_ingredient_shortage`, a starved furnace `no_ingredients`, and a furnace never fed has no recipe at all. Full result slots read `full_output`. `products_finished` counts **crafts, including productivity's bonus crafts**, not items: the harness multiplies by each product's amount. | Headless 2.0.77, 2026-10-11 (a plant at +175% made 13.73/s against 13.75/s expected). *Corrected 2026-10-12:* it was recorded as counting items until a cable plant (2 cables a craft) ran 60 crafts/s while its inserter moved 120 cable/s (`tests/test_harness_primitives.py`) |
| F19 | **2.0 effects are whole percents** (an `EffectValue` keeps two decimals; fixed in 2.1). A module's bonus × its quality multiplier is **truncated**. A beacon sends trunc(float32(Σ its modules × float32(effectivity))). The machine rounds Σ(sent × profile[N]) **half up, once**. Base + modules + beacons are then floored. So 2 legendary beacons give a plant speed 45.45, not 45.44. | Headless 2.0.77, 2026-10-11: matched 476 of 476 `LuaEntity.effects` values over 119 plants (every beacon quality, 1–6 beacons). Code: `effects.py`, switch `ROUND_2_0`; enforced by `tests/test_effects.py`. Untested: exact .5 ties, mixed beacon types. **Confirmed in-game 2026-10-12:** the user's Rate Calculator read 240.5 red circuits/s from the red block's 8 legendary plants (4, 4, 4, 5 legendary beacons a row), the solver's 2 × 120.27 |
| F20 | **Quality** (levels 0/1/2/3/5 for normal…legendary) multiplies crafting speed and module **bonuses** by 1 + 0.3·level, including efficiency's consumption cut, but not penalties and not crafting-machine power. Beacon effectivity is 1.5 + 0.2·level (legendary 2.5), and beacon power scales by `beacon_power_usage_multiplier` (legendary 1/6: 80 kW). | Headless 2.0.77, 2026-10-11 (`effects.py`) |
| F21 | **Productivity is capped at +300%** (4× output per craft). A machine's base productivity (electromagnetic plant +50%) applies even to recipes that refuse productivity modules. Nothing researches circuit or cable productivity. | Headless 2.0.77, 2026-10-11 (output 4× per craft at an uncapped 375%; an accumulator in a plant got +50%). Confirmed in-game 2026-10-12: the Rate Calculator's 174.9/s green and plastic for 240.5 red/s is 2 per craft at +175% (base +50%, 5 legendary prod-3) |
| F22 | **Machine power** = `energy_usage` × max(0.2, 1 + consumption) + drain, where drain defaults to `energy_usage`/30. A legendary plant with 5 legendary prod-3 and 1 legendary beacon draws 17,066.7 kW. | Headless 2.0.77, 2026-10-11 (network statistics; `effects.py`) |
| F23 | **"Research all"** sets each infinite technology to level 1 (+10% to 18 recipes, steel among them), belt stack size +3, inserter stack size +3 and bulk inserter capacity +11. | Technology Lua (`effects.TECHNOLOGIES`, checked against the files by a test); headless 2.0.77, 2026-10-11 |
| F24 | **Beacon reach:** a beacon supplies its footprint grown by `supply_area_distance` on every side (9×9 for the 3×3 beacon) and reaches every machine whose collision box overlaps it, corners included: up to 2 tiles of gap. Quality changes neither beacon reach nor module slots. Assembling machine 1, stone and steel furnaces and the burner drill take no beacon effects. | Headless 2.0.77, 2026-10-11 (boundaries for assembler 3, EM plant, lab, recycler). Confirmed in-game 2026-10-12 (the red block's 4, 4, 4, 5 beacons a row, counted from the geometry: the game's rate matches them, F19). Code: `checks.beacon_targets`; enforced by `beacon_reach` |
| F25 | **Module limits:** only a module's **bonuses** must be allowed, by the entity's `allowed_effects` and by the recipe's `allow_*` flags (productivity defaults to off). Beacons allow consumption, speed and pollution, so speed and efficiency modules go in and productivity and quality don't. Setting a recipe that refuses productivity ejects prod modules. | Headless 2.0.77, 2026-10-11 (`can_insert`). Enforced by `module_validity` |
| F26 | **Underground pairing:** an underground pairs with the first same-tier underground on its line. Other tiers and perpendicular ones are passed under; a same-tier entrance, or either kind facing back, blocks the pair. Ambiguous ghosts can flip type when revived. | Headless 2.0.77, 2026-10-11 (`neighbours`); confirmed in-game in the red circuit block, 2026-10-12 (all 8 of its undergrounds paired). Enforced by `underground_pairing` |
| F27 | **Hidden entities** can't be built in survival. 2.0.77 hides them through their **item's** `hidden`: the loaders (turbo included), loader-1x1, the infinity, linked and bottomless chests, the energy interfaces, and the space-platform hub. | Prototype data; matched `LuaEntityPrototype.hidden` headless 2.0.77, 2026-10-11. Enforced by `hidden_entities` |
| F28 | **Legendary stack inserter rates** with everything researched (hand 16, belt stack 4): **87.47/s** from a full stacked turbo belt into a machine, **120/s** machine to machine (inserters add up: 2 move 240, 3 move 360), **80/s** onto an empty stacked turbo lane. It drops onto the far lane only (F1), and the lane caps at 120/s, so a second inserter on that lane adds 40/s and a third adds nothing: filling both lanes (240/s) takes 2 inserters per lane, one set on each side of the belt. | Headless 2.0.77, 2026-10-12 (micro-blueprints with script-fed and drained machines, so the inserter is the only bottleneck; repeats exactly). In-game, the circuit block, 2026-10-12: 2 inserters per lane filled both lanes, as sized from these rates. Again in the optimiser's pick, 2026-10-12: **one** iron inserter (87.47/s against 87.27/s needed, 0.2% spare) kept the circuit plant fed at 240/s, as the harness predicted; again in the red circuit block, 2026-10-12 (1 hand-off inserter a link kept every red plant in cable). Code: `effects.LEGENDARY_STACK_INSERTER`; enforced by `tests/test_harness_primitives.py` |
| F29 | **Legendary long-handed inserter rate** with everything researched (hand 4: 1 + 3 researched, one stacked belt slot): **13.33/s** from a full stacked turbo belt 2 tiles out into a machine. Two on the same machine edge add up (26.67/s). So one can't feed a red block's cable plant alone (the plan's 4 cable plants need about 15.9 copper/s each at 240/s, `docs/red-circuits-plan.md`), and two can. | Headless 2.0.77, 2026-10-12 (a 4-beacon cable plant far faster than the inserters, output drained by script, nothing on the tile between the belt and the inserter; 1 and 2 inserters, each repeats exactly). Confirmed in-game 2026-10-12 (2 per cable plant kept the red block at 240.5/s). Code: `effects.LEGENDARY_LONG_INSERTER`; enforced by `test_long_handed_inserters_take_13_per_second_each_from_a_full_stacked_belt` in `tests/test_harness_primitives.py` |
| F30 | **A stack inserter takes as much from a mixed belt.** With green on one lane and plastic on the other (side-loaded from opposite sides, F3), a legendary stack inserter (hand 16) moves **87.47/s** into a machine, the same as from a one-item belt (F28), even though its hand holds one item, so each swing takes from one lane. Into a red circuit plant (2 green and 2 plastic a craft) that's 43.67/s of each. A red plant with 4 or 5 beacons eats 42.5 or 47.4/s of the two together, so one inserter feeds it with about 1.8× to spare. | Headless 2.0.77, 2026-10-12 (a red plant sped past the inserter with 5 speed modules and 11 beacons, cable fed and output drained by script, so it waited on the inserter for 6.75% of the window; repeats exactly). The harness counts an inserter's items, not which ones: the split comes from the plant's 21.83 crafts/s. Confirmed in-game 2026-10-12 (1 per red plant from the mixed belt kept the red block at 240.5/s). Code: `effects.LEGENDARY_STACK_INSERTER["mixed_belt_to_machine"]`; enforced by `test_one_inserter_takes_87_per_second_from_a_mixed_belt` in `tests/test_harness_primitives.py` |

## Techniques

### T1. Lane balancing: priority splitter and side-load
**Solves:** machines that unload with inserters from one side fill only the belt's far lane (F1). Output is capped at half a belt, and once that lane is busy, the last machines can't unload.

**Applies when:** any belt that inserters drop onto from one side, when the output can exceed one lane. Not needed for the steel column (T4), whose output is a fifth of its input.

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
- Near a full belt, the last inserters may find few gaps in the far lane. Not seen yet: at a full yellow belt (iron 15/s, 24 furnaces), every furnace could still unload. Still best-effort (P2).

**Status:** confirmed in-game 2026-10-11 on all 3 samples: copper 30/s (red belt, 48 furnaces), iron 15/s (yellow, 24 furnaces: both lanes 100% full, every furnace unloading) and steel 3/s (24 furnaces, every furnace unloading). Shown to us by the user.

**Code:** `generators/smelting_column.py` (`SPLITTER_ROW`, `SIDELOAD_ROW`, `SPLITTER_PRIORITY`, `_splitter_for`).
**Enforced by:** `check_flow` (splitter faces south across cols 5-6 with west priority; an east-facing side-load belt sits under every splitter). Tests: `test_module_layout_balances_lanes`, `test_broken_lane_balancing_is_rejected`, `test_missing_sideload_belt_is_rejected`.

### T2. Paired inserters at the machine boundary
**Solves:** a 3-tile machine column has no spare rows for poles or the T1 splitter.

**Layout:** machine A unloads from its bottom row and machine B from its top row, so the 2 inserters on each side sit together (rows 2-3 above). That frees rows 1, 4 and 5 for the pole (T3) and the splitter and side-load (T1).

**Status:** confirmed in-game 2026-10-11 (copper, iron and steel samples). Shown to us by the user, as part of T1.
**Code:** `generators/columns.py` (`modules`), shared by `smelting_column` and `steel_column`. **Enforced by:** each generator's `check_flow` (inserter pickup and drop columns) and `inserter_wiring`.

### T3. Pole ladder
**Solves:** powering a long column with as few poles as possible, and getting the wires into the blueprint (F6).

**Layout:** a medium pole in each inserter column on row 1 of every 2-machine module, which puts them 6 rows apart (reach 9, F10). The smelting column has 2 inserter columns (cols 1 and 5); the steel column has 3 (cols 1, 5 and 9) and needs all 3 poles, because a pole only reaches 3 tiles either side. The pipeline wires them axis-only into a ladder: rungs across each module, plus a rail down each inserter column.

**Status:** confirmed in-game 2026-10-11 (every sample fully powered, including the 24-furnace iron and steel columns and the 3-pole steel-from-ore column).
**Code:** poles in each generator (`POLE_ROW` in `generators/columns.py`); wiring in `pipeline.build` (`generate_power_connections(only_axis=True)`). **Enforced by:** `power_coverage` and `pole_network` in `checks.py`. Tests: `test_column_poles_are_wired_as_a_ladder`, `test_poles_form_one_network`, `test_power_reach_is_measured_from_the_pole_centre`.

### T4. Direct insertion furnace chain
**Solves:** making steel from ore without a plate belt in between.

**Layout:** each iron furnace hands its plates straight to the steel furnace beside it through one inserter. One module is two pairs, 11 tiles wide:

```
col:  0  1  2-4      5  6-8       9  10
row0  v  .  [IRON A] .  [STEEL A] .  v
row1  v  P  [IRON A] P  [STEEL A] P  v
row2  v  I  [IRON A] I  [STEEL A] I  v
row3  v  I  [IRON B] I  [STEEL B] I  v
row4  v  .  [IRON B] .  [STEEL B] .  v
row5  v  .  [IRON B] .  [STEEL B] .  v

col 0 ore belt, col 10 steel belt, both south.   I inserter (moves west to east)   P medium pole
```

**Why it works:** an iron furnace makes exactly what a steel furnace eats (F12), so pairs never starve or back up. Each furnace picks its recipe from what it's fed (F13). A full yellow belt of ore (15/s) feeds 24 pairs for 3 steel/s.

**Gotchas:**
- The generator refuses a furnace whose iron and steel rates don't match 1:1, for example a modded recipe.
- No lane balancing on the steel belt (T1 skipped): 3 steel/s from a full yellow belt of ore is well under one lane.
- The middle inserter column needs its own pole (T3).

**Status:** confirmed in-game 2026-10-11 (3 steel/s from a full yellow belt of ore, 24 pairs: every furnace running). Chosen by the user over a middle plate belt.

**Code:** `generators/steel_column.py`.
**Enforced by:** `check_flow` (inserters move ore -> iron -> steel -> belt; every iron furnace has a steel partner; every furnace is loaded and unloaded; both belts flow south). Tests: `test_broken_layout_is_rejected` in `tests/test_steel_column.py`.

### T5. Side-load stub for the second lane
**Solves:** filling both lanes of an output belt from a single machine. Its inserters all sit on one side of the belt, so they fill only the far lane (F1), and a 4×4 machine has no spare rows for T1's splitter.

**Layout** (the circuit block; the output belt flows south down x=5):

```
     x  0  1  2  3  4  5
y -3    .  .  .  .  .  v      the output belt starts above the stub, so (5,-2) is straight
y -2    .  .  >  >  >  v      stub: flows east into the output belt's side, from under its first inserter
y -1    .  .  ^  ^  .  v      2 inserters fill the stub, at the plant's east end
y  0    C  C  C  C  >  v      2 inserters fill the east (far) lane
y  1    C  C  C  C  >  v
```

**Why it works:** side-loading puts everything onto the receiving belt's near lane (F3), which is the west lane here, and the east inserters fill the far lane. Each lane gets 2 inserters: 80/s plus the remaining 40/s reaches the 120/s stacked cap (F28).

**Gotchas:**
- **The output belt must run straight past the side-load tile.** Without the belt above it, the stub turns into the output belt instead of side-loading, and keeps its lane, which is the east one. `check_flow` requires that belt.
- The machine is over-capacity against a full belt (250/s against 240/s), so it's blocked on output a few percent of the time (1.8% measured), under the 5% bar.
- **Keep the stub short: put its inserters at the end of the machine's edge nearest the output belt, and start the stub under the first one.** Stub belt upstream of the first inserter carries nothing. With 2 inserters at x=2–3, the stub is 3 tiles instead of 5. *Taught by the user 2026-10-12, with an in-game screenshot of their tweak of the optimiser's pick: "save 2 green belts".*

**Status:** **confirmed in-game 2026-10-12** (the default circuit block, legendary: both output lanes full, the stub side-loading onto the west lane; the user: "It works perfectly"). Headless 2.0.77 agrees: lanes 120.00/120.00, and with 1 stub inserter they read 120/80. Layout approved by the user 2026-10-12. The north layout (T6) keeps the stub unchanged: lanes 120.00/120.00 headless, 2026-10-12. **The short stub** (inserters at x=2–3, stub x=2–4): confirmed in-game 2026-10-12 in the user's own tweak (their screenshot: both output lanes full), and headless 2.0.77 agrees (lanes 120/120 for west and north).

**Code:** `generators/circuit_block.py` (`CIRCUIT_EAST`, `stub_from`). **Enforced by:** its `check_flow`: a stub inserter, the output belt running straight past the stub, belt directions, no stub belt west of the first stub inserter, and no gap in the stub. Tests: `test_broken_layout_is_rejected` (the stub run back to x=0, a missing stub tile), `test_stub_starts_under_its_first_inserter` and `test_one_stub_inserter_fails_short_and_the_balancer_evens_its_lanes` in `tests/test_circuit_block.py`.

### T6. Copper from the north (compact circuit block)
**Solves:** the west-fed circuit block spends 2 columns on its copper belt and inserter, beside the cable plant. That makes the block 13×11 when nothing else needs those columns.

**Layout** (`copper: "north"`; otherwise identical to the west layout, coordinates as in `generators/circuit_block.py`):

```
     x -5 -4 -3 -2 -1  0
y -2    Cu  S  S  .  .  .     a one-tile copper belt flows east; its front is the substation
y -1     v  S  S  .  .  .     the copper inserter picks up from the north (F7)
y  0     K  K  K  K  >  C
...
y  5    Fe  >  >  >  >  >     the iron belt now starts at x=-5
```

**Why it works:** the beacons need 2 rows of gap above the plants anyway (F24), and the substation uses only 2 of the 4 tiles in those rows above the cable plant. The copper belt and inserter take the gap column at x=-5, so the block loses 2 columns: 11×11 = 121 tiles against 143. At 240/s the machines and beacons can't shrink (1 beacon caps the circuit plant at 179/s), so input routing is the only footprint lever.

**Gotchas:**
- The copper belt sits on the stub's row (y=-2). `check_flow` resolves the copper role before the stub role, and the stub is only x 0–4.
- There must be exactly one copper belt (west or north). `check_flow` checks that.

**Status:** layout approved by the user 2026-10-12. Headless 2.0.77, 2026-10-12: 239.74/s crafted, lanes 120.00/120.00, circuit plant blocked 1.8%. `blueprint-smith optimise` picks it for 240/s. **Confirmed in-game 2026-10-12** (the optimiser's pick, with 1 iron inserter: "It worked well"; the user's screenshot shows both output lanes full and the copper inserter feeding the cable plant from the north).

**Code:** `generators/circuit_block.py` (`COPPER_BELTS`, `COPPER_INSERTERS`, `IRON_FROMS`). **Enforced by:** `check_flow` (exactly one copper belt, and copper → cable plant). Tests: `test_broken_north_layout_is_rejected` and the north footprint and harness tests in `tests/test_circuit_block.py`.

### T7. More output inserters down a filling lane
**Solves:** a row of plants sharing one output lane. Each plant drops onto the lane its upstream neighbours have already partly filled, so the last plants find few free slots (F1, F28). They sit blocked on output, and the lane never fills.

**Sizing (inferred, best-effort):** a plant's n output inserters carry n × 80/s (F28) times the share of the lane still free where the lane reaches it. In the red block the last plant meets a lane 73% full: one inserter gets 21.7/s against the 32.5/s it makes, and two get 43.4/s. So it uses 2 output inserters a plant.

**Status:** headless 2.0.77, 2026-10-12, in the red block (4 plants a row onto a 120/s stacked lane):
- **1 output inserter a plant:** 233.19/s (97.2%), lanes 116.87/116.40, and the last plant blocked 6.4%. It fails.
- **2 a plant:** 237.80/s (99.1%), lanes 119.07/118.67, and no plant blocked over 1.3%. It passes.

The free-slot model is more pessimistic than the game (one inserter measured about 30/s, not 21.7/s), so it can reject a variant the harness would pass. **The lane reset (T12) is the better fix:** with it the far lane is empty again halfway, so 1 output inserter a plant is enough (confirmed in-game 2026-10-12). `sizing` credits it: the far lane's fill restarts at the reset. **Confirmed in-game 2026-10-12** (the red block with 2 output inserters a plant: both output lanes full at 240.5/s, so no row's last plant held it back).

**Code:** `generators/plant_array.py` (`sizing`, its `room`). **Enforced by:** the notes' `WARNING` and `variants`. Tests: `test_one_output_inserter_is_warned_about_on_a_filling_lane`, and the harness test `test_one_output_inserter_a_plant_falls_short_on_the_filling_lane` in `tests/test_plant_array.py`.

### T8. Two items on one belt, one per lane
**Solves:** feeding a row of plants two ingredients from one belt, such as green and plastic for red circuits. Each item needs its own lane, because an item allowed onto both lanes can clog the other item out.

**Layout:** a one-tile riser M is the start of the row's mixed belt. One item side-loads it from the west and the other from the east, and nothing feeds it from behind, so it stays straight and each side-load fills only its own near lane (F3). M then turns onto the row (a curve keeps lanes).

```
     x -3 -2 -1
y -2     .  >  .     M turns east: the near belt
y -1     >  ^  <     green from the west, plastic from the east, nothing behind M
```

**Merge early.** Put M where the two items' belts first sit side by side, and run one mixed belt from there. The red block's row B used to run green and plastic as two belts down to the row and merge there. The user moved its M up to where both surface from under the beacon row (y=10), and one belt runs down x=-2: 5 belts fewer (their in-game copy, 2026-10-12).

**Gotchas:**
- With only one side input and nothing behind, M turns into a curve and the item keeps both its lanes. That's fine for a single item (green circuits on the array), but it's wrong for two.
- Each side-load caps its item at one lane: 120/s stacked. That's why the red block has two rows: green alone is 174.5/s.

**Status:** headless 2.0.77, 2026-10-12. The red block's rows are fed this way, and the block passes (F30 measured the mixed belt). Row B's early M ran in the user's own in-game copy, 2026-10-12 (their screenshot). **Confirmed in-game as generated, 2026-10-12** (both rows' mixed belts kept 8 red plants at 240.5/s, both output lanes full).

**Code:** `generators/plant_array.py` (the front end, `M_X`, `M_B_Y`). **Enforced by:** its `check_flow` (each row's riser, both feeders, nothing behind, and row B's run down to its near belt unbroken). Tests: `test_broken_layout_is_rejected` (a feeder removed from each row, a belt behind M, a gap in row B's run) in `tests/test_plant_array.py`.

### T9. Merging two rows' outputs onto one belt
**Solves:** two rows of plants that face a shared beacon row each fill the lane of their own output belt nearest the beacons (F1). So both rows' items sit on the "inner" lane, and a plain merge would put them on the same lane.

**Layout** (the red block's east end; x=33, y=7 is the generator's output port, before the lane balancer, T11):

```
     x 32 33
y  5    >  v     output A turns south past the beacon row's end
y  6    B  v
y  7    B  >     both side-load the middle belt from opposite sides: A its north lane, B its south lane (F3)
y  8    B  ^
y  9    >  ^     output B turns north
```

- The middle belt has nothing behind it (the beacon row), so with both sides feeding it, it stays straight and each side-load keeps its own lane.
- No undergrounds. The user's, from their in-game copy (2026-10-12), replacing a merge that took output A under output B with an underground pair.

**Gotchas:** both turn-ins are needed. With only one, the middle tile becomes a curve, and the other row has nowhere to go.

**Status:** the user's own in-game copy ran with it, 2026-10-12 (their screenshot). Headless 2.0.77, 2026-10-12: 238.09/s, lanes 119.00/119.07 in the red block with it. **Confirmed in-game as generated, 2026-10-12** (240.5/s, both output lanes full after the balancer).

**Code:** `generators/plant_array.py` (the east merge, `merge_x`, `MERGE_Y`). **Enforced by:** `check_flow`: the middle tile flowing east, both outputs' last tiles turning in, and both turn-ins present. Tests: `test_broken_layout_is_rejected` in `tests/test_plant_array.py`.

### T10. Long-handed reach for a machine with no belt of its own
**Solves:** in a row, a machine's short sides face its neighbours and its long sides face the row's two belts. A cable plant handing cable sideways to the red plants either side of it has no belt left for its copper.

**Layout:** a copper belt one row further out than the near belt. The cable plant's long-handed inserters reach over the near belt (F29: 13.33/s each, so 2 per cable plant at 240/s).

**Gotchas:**
- The input side is 3 rows deep (far belt, near belt, inserters). A beacon reaches across at most 2 tiles of gap (F24), so the beacons go on the output side.
- A stack inserter in a long-handed inserter's place feeds the plant from the near belt instead.

**Status:** headless 2.0.77, 2026-10-12, with the full near belt in between (the red block passes). **Confirmed in-game 2026-10-12** (2 long-handed inserters a cable plant kept the red block at 240.5/s).

**Code:** `generators/plant_array.py`. **Enforced by:** `check_flow` (far belt → intermediate plant only). Tests: `test_broken_layout_is_rejected` (a stack inserter swapped in) in `tests/test_plant_array.py`.

### T11. Lane balancer at the end of an output
**Solves:** an output belt whose lanes carry different amounts, for example when one of two rows makes less than the other (P4).

**Layout** (an output flowing south; the old end is `o`, the new output port `O`):

```
     o            the generator's last belt
    [S S]         a splitter: the old end's column and the one to the flow's right
     v > v        the right half runs on; the left half curves out to the left
     > O <        both turn back in and side-load O from opposite sides (F3)
```

- The splitter halves each lane, so each half carries half of both lanes. Each half then side-loads one whole lane of `O`, so both lanes get the same: (left + right) / 2.
- 3 tiles wide, centred on the output's line, and 3 tiles long. The output leaves in line with where it came in.

**Gotchas:**
- `O` must have no belt behind it, or the turn-ins become curves instead of side-loads. The left half's curve out sits behind it, flowing across, so it doesn't feed it.
- It widens a block whose output runs along its edge by a column, like the circuit block (13 × 11 → 14 × 14 with the 3 rows).

**Status:** the user's own build, 2026-10-12 (a screenshot of one on their copy of the red circuit block). Generated balancers headless 2.0.77, 2026-10-12: the full suite's harness runs pass with one on every output, and the under-sized circuit block's 120/80 lanes leave it at 100.0/100.0. **Confirmed in-game as generated, 2026-10-12** (the red block: "The balancer works", both output lanes full at 240.5/s).

**Code:** `pipeline.balancers` (`_balancer_layout`). **Enforced by:** `pipeline.check_balancers`; tests `test_every_output_ends_in_a_lane_balancer` and `test_wrong_balancers_are_rejected` in `tests/test_ports.py`.

### T12. Lane reset halfway along a filling output belt
**Solves:** a row of machines unloading onto one lane of a belt. The lane fills as it goes, so the last machines' inserters wait for gaps (T7), even when the row's total fits the lane. The user saw the red block's output inserters "often waiting because the belt is full" in-game.

**Layout:** T1's priority splitter and side-load, once, halfway along the row. In the red block it goes after the 2nd of 4 red plants (row A; row B mirrors it, prioritising south):

```
     x 12 13 14
y  3    P  P  P     (red plants 2 and 3)
y  4    i [S] v     the splitter's north half prioritised; it turns south
y  5    > [S] >     and side-loads its items onto the output belt's north lane (F3)
```

- The splitter sends everything on the far lane out its priority half, which side-loads it onto the near lane. The near lane is empty there, since the inserters only drop onto the far lane (F1).
- Past it, the far lane is empty again for the row's second half. The belt leaves with the first half on one lane and the second half on the other.
- 2 extra splitters and 2 belts in the block, on tiles the inserter rows weren't using.

**Gotchas:**
- The priority must point at the inserters' side, where the side-load belt is. Without it the splitter halves the far lane, and half of it stays full.
- The whole output belt still side-loads one lane at the merge (T9), so a row is still capped at 120/s. The reset only moves where the gaps are.

**Status:** the user's, 2026-10-12: they added it in-game to the red block after seeing the output inserters wait, and it "flows better with no idle output inserters" (their exported blueprint, which the generated block now matches entity for entity). Headless 2.0.77, 2026-10-12, red block with 2 output inserters a plant: 240.55/s crafted, 240.00/s delivered, lanes 120.00/120.00, every red plant 100% working and none blocked (without it: 238.09/s crafted, 1.1% blocked). **1 output inserter a plant is enough with it:** the user confirmed it in-game 2026-10-12 ("1 per plant works"). Headless 2.0.77 agrees once the growth bar allows for the inserter's hand (P2): 240.55/s crafted, lanes 120.00/120.00, none blocked. The optimiser now picks 1 a plant, 8 stack inserters fewer than before the reset.

**Code:** `generators/plant_array.py` (`reset_after`, `reset_column`). **Enforced by:** `check_flow` (one reset splitter per row after half its plants, prioritising the inserters' side, and its side-load belt). Tests: `test_broken_layout_is_rejected` (no priority, the wrong priority, no side-load belt, no reset) and the harness tests in `tests/test_plant_array.py`.

### H1. Headless evaluation harness
**Solves:** trusting a blueprint without the user importing it (v2 milestone 1, `PROJECT_BRIEF.md`).

**How it works:**
- The Factorio 2.0.77 headless server (Linux build, in `~/.cache/blueprint-smith/`; `blueprint-smith install-server` fetches it) runs a generated mod. The mod pastes the blueprint on a lab surface and revives it.
- Each input port is fed by a loader of its belt's tier from an infinity chest. Each output port drains through a loader into a chest that is emptied every tick.
- A port's `stack` (1–4) is items per belt slot. An input with `stack` > 1 gets no loader, since loaders can't output stacks: each tick the mod inserts a stack at the back of both lanes (F17). Outputs drain through the loader at any stack.
- `research` is `none` (the default, matching `ratios.py`) or `all` (M2 runs). The result records the research bonuses and each machine's quality, crafting speed and productivity.
- Every inserter's items moved are counted from its hand, which only shrinks when it lets go, with its hand size and statuses.
- *Measurement blueprints only:* `probes` script-feed chosen ingredients into a machine or empty its output every tick, so the link under test is the only bottleneck (F28).
- An energy interface on a pole is wired to the nearest blueprint pole.
- The run gets a warmup of max(2 min, 3 × belt transit, 10 × slowest craft), then a window of max(60 s, 10 × slowest craft).
- Over the window it measures:
  - Crafted rate: each machine's finished crafts plus progress, so crafts finishing in step don't alias.
  - Delivered rate and per-lane rate.
  - Each machine's status share and output-buffer growth (F15).
  - Where each machine unloads (into machines, onto belts, elsewhere), read from its inserters' targets at the end of the window.
  - Power.

**Status:**
- Calibrated 2026-10-11 against every confirmed in-game result. Iron 15/s, copper 30/s and both steel samples pass at exactly their target, both lanes full where T1 applies.
- Pre-T1 copper puts every plate on one lane (F1). Asked for a full belt it backs up, and unwired poles fail (F6).
- **Pre-T1 steel disagrees with the game** (see open questions).
- About 6 s per run, and runs work in parallel.
- **First assembler-type calibration point, 2026-10-12:** the harness passed the default circuit block (239.71/s, lanes 120/120), and it ran with both lanes full in the user's game. Until then every in-game confirmation was a furnace column.
- **First multi-plant beaconed block, 2026-10-12:** the red circuit array (8 red and 4 cable plants, two rows, a lane merge and an output merge) passed: 237.80/s (99.1%), lanes 119.07/118.67. With 1 output inserter a plant it failed at 97.2% (T7). The user ran a copy in-game with three cheaper changes (T8, T9, the front end's copper hop) and a lane balancer. With those adopted the harness gives 238.09/s, lanes 119.00/119.07. **The game agreed, 2026-10-12:** the generated block ran with both output lanes full, and the user's Rate Calculator read 240.5/s. With the user's lane reset (T12) as well: 240.55/s crafted, lanes 120.00/120.00, no red plant blocked. **The growth bar disagreed with the game once, 2026-10-12:** with 1 output inserter a plant the harness failed a red plant on 4 items of output growth, while the block ran fine in-game. Over 6× the window the growth stayed at 4–7 items, never building: that's a 16-item hand's swing. The bar now allows for the biggest hand unloading a machine (P2).
- **The optimiser's first pick agreed with the game, 2026-10-12:** the harness passed the north block with one iron inserter at 0.2% spare (240.01/s, lanes 120/120), a variant the static 98% margin warns about, and it ran well in the user's game.
- Stacked feed, 2026-10-11: a turbo belt fed at stack 4 delivers 240.00/s, 120/120 per lane, with or without research. Stack 1 through the loader gives 60/s. A legendary EM plant with 5 legendary prod-3 and 1 legendary beacon reads speed 32.5 and productivity +175%, as `effects.py` predicts.

**Code:** `src/blueprint_smith/harness/` (`mod/control.lua`, `runner.py`, `verdict.py`, `server.py`), `evaluate.py` (timing). Plan and spike notes: `docs/m1-harness-plan.md`.
**Enforced by:** `tests/test_harness_calibration.py` (real server; skipped without one), `tests/test_harness_m2.py` (stacked feed, legendary modules, a blocked plant), `tests/test_harness_primitives.py` (inserter rates, plant speed against the solver), `tests/test_harness_runner.py`, `tests/test_cli_evaluate.py`.

## Open questions

- How close to a full belt does T1 really get at the bottom of a long column? On a 24-furnace yellow column (iron 15/s), it reaches 100% of both lanes with every furnace unloading. The 48-furnace red column (copper 30/s) came out correctly, but nobody checked whether its bottom furnaces were blocked. Faster belts and longer columns are still open.
- Do other machine shapes (assemblers with several inputs, fluids) need a different balancing module? *Partly answered 2026-10-12:* the red circuit array balances by geometry instead. Each of its two rows fills one lane, and the rows merge (T9). The first plants of a row fill that lane, so later ones need more output inserters (T7). Fluids are still open.
- **Pre-T1 steel: the harness and the game disagree.** In-game (old single-sided layout, output consumed downstream) the last few furnaces couldn't unload. In the harness, with a free-draining sink, every furnace works, even after 20 minutes and with all research. 3/s on one lane of a 7.5/s belt should leave plenty of gaps. Possible causes: the downstream consumer backed up, the startup burst, or a mod. `test_pre_t1_steel_jams_like_in_game` is a strict xfail until this is settled. *Low priority:* the user confirmed (2026-10-11) the jam only ever happened on the pre-splitter layout, and every current generator uses T1.
- **Copper 30/s bottom furnaces:** never checked in-game for blocking. The harness says none are blocked, but the result only counts as ground truth once the user re-checks it.
- **Do empty or unpowered beacons count toward a machine's beacon number N?** `effects.py` assumes every beacon in reach counts. Untested.
