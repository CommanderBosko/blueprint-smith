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
2. **Every belt that inserters unload onto from one side needs lane balancing (T1) if its output can exceed one lane.** Otherwise only the far lane fills (F1). Skip T1 when the output can never fill one lane (the steel column's output is a fifth of its input).
3. **Input belts need nothing extra.** Inserters take from both lanes (F2).
4. **Leave rows for poles (T2, T3).** The pipeline wires them (F6), and `pole_network` fails any pole it misses. Supply reach is measured from the pole's centre (F10), so a medium pole covers 3 tiles either side of its own column.
5. **Use facing-relative left/right for splitter priority (F5).** Never assume screen left.
6. **Enforce every technique in code.** Each technique a generator uses gets an invariant in its `check_flow` and a mutation test that breaks the layout on purpose and expects the build to fail.
7. **Share code, don't copy it.** When a second generator needs a technique, move it out of the first generator into a shared building block.
8. **Record the in-game result here.** After the user tests a blueprint, update the status of every entry it exercised.
9. **Size beaconed machines with the solver, not by hand.** Count each machine's beacons with `checks.beacon_targets` (F24) and pass them to `effects.entity_rates` (F19–F21). The generic checks already enforce module limits, underground pairing and survival-buildable entities (F25–F27).

## Principles (the user's quality bar)

### P1. Use whole belts
Both output lanes should fill, the full input belt should be eaten, and no machine should be blocked from unloading. "Runs at the specified rate" isn't enough. *Set by the user, 2026-10-11, after the copper and steel samples ran but wasted half of each belt.*

### P2. Two-tier acceptance
- **Guaranteed by the tooling:** a valid string that round-trips, no collisions, everything connected and powered, ratios computed.
- **Best-effort:** real throughput. Report it as `WARNING:` notes, never as failures, and never claim more than that. *From `PROJECT_BRIEF.md`.*
- **Amended for v2, in effect since 2026-10-11 (H1):** a headless harness run (`blueprint-smith evaluate`, `build --evaluate`) is a hard pass/fail. Builds checked only statically keep the `WARNING:` notes. A run fails if:
  - the crafted output is below 98% of the target (the sink rate when no machine makes the item);
  - any machine is blocked on output (`full_output`, `waiting_for_space_in_destination`, `full_burnt_result_output`) for more than 5% of the window;
  - any machine's output backs up (more than 3 items gained);
  - or less than 80% of the crafted output reaches the output port.

  Idle time isn't failed: beacons come in whole steps, so an honest design runs some machines under capacity. Each machine kind's utilisation (min and mean share working) is reported instead, and the output bar catches a starved line. Unpowered time isn't judged either, only reported: power is never short in the user's save (user, 2026-10-12). *The M2 machine bar was decided by the user and implemented 2026-10-11. It replaced "every machine working at least 95%".*

## Game mechanics

| # | Fact | Status |
|---|---|---|
| F1 | **Inserters drop onto the far lane** of a belt. | Confirmed in-game 2026-10-11 (copper 15/s: every plate on one lane) |
| F2 | **Inserters pick up from both lanes.** | Confirmed in-game 2026-10-11 (steel 3/s drained a full yellow belt of iron plates, on both the old and lane-balanced layouts) |
| F3 | **Side-loading:** a belt feeding into the side of another puts everything onto the receiving belt's near lane. | Confirmed in-game 2026-10-11 (T1: copper 30/s, iron 15/s, steel 3/s) |
| F4 | **Splitters keep lanes:** an item leaves on the same lane it entered. | Game rule, relied on by T1; not tested separately |
| F5 | **Splitter `output_priority` "left"/"right" is relative to the splitter's facing.** Facing south, `"right"` is the west output. | Confirmed in-game 2026-10-11 (priority arrows on the west half) |
| F6 | **A pasted blueprint keeps only the wires it carries.** Poles inside it don't auto-connect, even within reach. | Confirmed in-game 2026-10-11 (11 of 12 poles dead before the pipeline added wires) |
| F7 | An inserter's blueprint `direction` is the side it **picks up from**. | Prototype data; every in-game test so far flowed correctly |
| F8 | Directions: N=0, NE=2, E=4, S=8, W=12. | Prototype data |
| F9 | Underground belt `max_distance` is 5/7/9/11 tiles for yellow/red/blue/turbo, from entrance to exit (total span, not the gap). | Prototype data; headless 2.0.77, 2026-10-11 (yellow pairs at 5 not 6, turbo at 11 not 12) |
| F10 | Medium electric pole: 7x7 supply area, wire reach 9. The supply area spans `supply_area_distance` either side of the pole's **centre**, not its edge (small 5x5, medium 7x7, big 4x4, substation 18x18). | Prototype data; poles 6 rows apart confirmed in-game 2026-10-11. `power_coverage` measured from the edge until 2026-10-11, found by the steel column's mutation test |
| F11 | One belt lane carries `speed x 60 x 4` items/s: 7.5 yellow, 15 red, 22.5 blue, 30 turbo. A full belt carries double. | Prototype data (`ratios.belt_lane_capacity`); full yellow belt (15/s) confirmed in-game 2026-10-11 (iron, both lanes full) |
| F12 | Electric furnace: 3x3, crafting speed 2. Iron and copper plate take 3.2 s (0.625/s each); steel takes 16 s and 5 iron plates (0.125/s each). So one iron furnace makes exactly what one steel furnace eats (0.625 plates/s), at any crafting speed. | Prototype data; iron confirmed in-game 2026-10-11 (24 furnaces filled both lanes of a yellow belt); 1:1 pairing confirmed in-game 2026-10-11 (steel column, every furnace running) |
| F13 | **Furnaces pick their recipe from their input:** ore makes plates, iron plates make steel. Blueprints don't set a furnace recipe. | Confirmed in-game 2026-10-11 (steel column: ore-fed furnaces made plates, plate-fed furnaces made steel) |
| F14 | **Research changes throughput.** Space Age's steel-plate productivity research adds +10% steel at level 1, and inserter capacity research raises hand size. `ratios.py` assumes no research, so the harness defaults to none (`--research all` researches everything). `effects.py` models research for M2 (F23). | Headless 2.0.77, 2026-10-11 (steel furnaces made 11 crafts in 80 s with all research, 10 without) |
| F15 | **A machine buffers a stack of output** (100 plates is about 160 s of an iron furnace, 800 s of a steel one). A furnace whose output is blocked keeps crafting into that buffer and still reads "working", so a jam can hide for minutes. Watch the buffer grow instead. | Headless 2.0.77, 2026-10-11 (pre-T1 copper asked for 30/s: every furnace "working" while the bottom 24 gained 38 plates each) |
| F16 | **A script-revived blueprint keeps** splitter `output_priority` and the copper wires it carries, and fulfilling module requests by script keeps their quality. | Headless 2.0.77, 2026-10-11 |
| F17 | **A script can stack items on a belt without a loader or research:** `insert_at_back({name, count=4}, 4)` once per lane per tick holds a turbo belt at 240/s (120 per lane). A turbo loader drains a stacked belt at the full 240/s, so only the feed side needs the script. | Headless 2.0.77, 2026-10-11 (`tests/test_harness_m2.py`) |
| F18 | **Statuses:** a starved assembler reads `item_ingredient_shortage`, a starved furnace `no_ingredients`, and a furnace never fed has no recipe at all. Full result slots read `full_output`. `products_finished` counts **crafts, including productivity's bonus crafts**, not items: the harness multiplies by each product's amount. | Headless 2.0.77, 2026-10-11 (a plant at +175% made 13.73/s against 13.75/s expected). *Corrected 2026-10-12:* it was recorded as counting items until a cable plant (2 cables a craft) ran 60 crafts/s while its inserter moved 120 cable/s (`tests/test_harness_primitives.py`) |
| F19 | **2.0 effects are whole percents** (an `EffectValue` keeps two decimals; fixed in 2.1). A module's bonus × its quality multiplier is **truncated**. A beacon sends trunc(float32(Σ its modules × float32(effectivity))). The machine rounds Σ(sent × profile[N]) **half up, once**. Base + modules + beacons are then floored. So 2 legendary beacons give a plant speed 45.45, not 45.44. | Headless 2.0.77, 2026-10-11: matched 476 of 476 `LuaEntity.effects` values over 119 plants (every beacon quality, 1–6 beacons). Code: `effects.py`, switch `ROUND_2_0`; enforced by `tests/test_effects.py`. Untested: exact .5 ties, mixed beacon types |
| F20 | **Quality** (levels 0/1/2/3/5 for normal…legendary) multiplies crafting speed and module **bonuses** by 1 + 0.3·level, including efficiency's consumption cut, but not penalties and not crafting-machine power. Beacon effectivity is 1.5 + 0.2·level (legendary 2.5), and beacon power scales by `beacon_power_usage_multiplier` (legendary 1/6: 80 kW). | Headless 2.0.77, 2026-10-11 (`effects.py`) |
| F21 | **Productivity is capped at +300%** (4× output per craft). A machine's base productivity (electromagnetic plant +50%) applies even to recipes that refuse productivity modules. Nothing researches circuit or cable productivity. | Headless 2.0.77, 2026-10-11 (output 4× per craft at an uncapped 375%; an accumulator in a plant got +50%) |
| F22 | **Machine power** = `energy_usage` × max(0.2, 1 + consumption) + drain, where drain defaults to `energy_usage`/30. A legendary plant with 5 legendary prod-3 and 1 legendary beacon draws 17,066.7 kW. | Headless 2.0.77, 2026-10-11 (network statistics; `effects.py`) |
| F23 | **"Research all"** sets each infinite technology to level 1 (+10% to 18 recipes, steel among them), belt stack size +3, inserter stack size +3 and bulk inserter capacity +11. | Technology Lua (`effects.TECHNOLOGIES`, checked against the files by a test); headless 2.0.77, 2026-10-11 |
| F24 | **Beacon reach:** a beacon supplies its footprint grown by `supply_area_distance` on every side (9×9 for the 3×3 beacon) and reaches every machine whose collision box overlaps it, corners included: up to 2 tiles of gap. Quality changes neither beacon reach nor module slots. Assembling machine 1, stone and steel furnaces and the burner drill take no beacon effects. | Headless 2.0.77, 2026-10-11 (boundaries for assembler 3, EM plant, lab, recycler). Code: `checks.beacon_targets`; enforced by `beacon_reach` |
| F25 | **Module limits:** only a module's **bonuses** must be allowed, by the entity's `allowed_effects` and by the recipe's `allow_*` flags (productivity defaults to off). Beacons allow consumption, speed and pollution, so speed and efficiency modules go in and productivity and quality don't. Setting a recipe that refuses productivity ejects prod modules. | Headless 2.0.77, 2026-10-11 (`can_insert`). Enforced by `module_validity` |
| F26 | **Underground pairing:** an underground pairs with the first same-tier underground on its line. Other tiers and perpendicular ones are passed under; a same-tier entrance, or either kind facing back, blocks the pair. Ambiguous ghosts can flip type when revived. | Headless 2.0.77, 2026-10-11 (`neighbours`). Enforced by `underground_pairing` |
| F27 | **Hidden entities** can't be built in survival. 2.0.77 hides them through their **item's** `hidden`: the loaders (turbo included), loader-1x1, the infinity, linked and bottomless chests, the energy interfaces, and the space-platform hub. | Prototype data; matched `LuaEntityPrototype.hidden` headless 2.0.77, 2026-10-11. Enforced by `hidden_entities` |
| F28 | **Legendary stack inserter rates** with everything researched (hand 16, belt stack 4): **87.47/s** from a full stacked turbo belt into a machine, **120/s** machine to machine (inserters add up: 2 move 240, 3 move 360), **80/s** onto an empty stacked turbo lane. It drops onto the far lane only (F1), and the lane caps at 120/s, so a second inserter on that lane adds 40/s and a third adds nothing: filling both lanes (240/s) takes 2 inserters per lane, one set on each side of the belt. | Headless 2.0.77, 2026-10-12 (micro-blueprints with script-fed and drained machines, so the inserter is the only bottleneck; repeats exactly). Code: `effects.LEGENDARY_STACK_INSERTER`; enforced by `tests/test_harness_primitives.py` |

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
  - Power.

**Status:**
- Calibrated 2026-10-11 against every confirmed in-game result. Iron 15/s, copper 30/s and both steel samples pass at exactly their target, both lanes full where T1 applies.
- Pre-T1 copper puts every plate on one lane (F1). Asked for a full belt it backs up, and unwired poles fail (F6).
- **Pre-T1 steel disagrees with the game** (see open questions).
- About 6 s per run, and runs work in parallel.
- Stacked feed, 2026-10-11: a turbo belt fed at stack 4 delivers 240.00/s, 120/120 per lane, with or without research. Stack 1 through the loader gives 60/s. A legendary EM plant with 5 legendary prod-3 and 1 legendary beacon reads speed 32.5 and productivity +175%, as `effects.py` predicts.

**Code:** `src/blueprint_smith/harness/` (`mod/control.lua`, `runner.py`, `verdict.py`, `server.py`), `evaluate.py` (timing). Plan and spike notes: `docs/m1-harness-plan.md`.
**Enforced by:** `tests/test_harness_calibration.py` (real server; skipped without one), `tests/test_harness_m2.py` (stacked feed, legendary modules, a blocked plant), `tests/test_harness_primitives.py` (inserter rates, plant speed against the solver), `tests/test_harness_runner.py`, `tests/test_cli_evaluate.py`.

## Open questions

- How close to a full belt does T1 really get at the bottom of a long column? On a 24-furnace yellow column (iron 15/s), it reaches 100% of both lanes with every furnace unloading. The 48-furnace red column (copper 30/s) came out correctly, but nobody checked whether its bottom furnaces were blocked. Faster belts and longer columns are still open.
- Do other machine shapes (assemblers with several inputs, fluids) need a different balancing module? Revisit with the next generator.
- **Pre-T1 steel: the harness and the game disagree.** In-game (old single-sided layout, output consumed downstream) the last few furnaces couldn't unload. In the harness, with a free-draining sink, every furnace works, even after 20 minutes and with all research. 3/s on one lane of a 7.5/s belt should leave plenty of gaps. Possible causes: the downstream consumer backed up, the startup burst, or a mod. `test_pre_t1_steel_jams_like_in_game` is a strict xfail until this is settled. *Low priority:* the user confirmed (2026-10-11) the jam only ever happened on the pre-splitter layout, and every current generator uses T1.
- **Copper 30/s bottom furnaces:** never checked in-game for blocking. The harness says none are blocked, but the result only counts as ground truth once the user re-checks it.
- **Do empty or unpowered beacons count toward a machine's beacon number N?** `effects.py` assumes every beacon in reach counts. Untested.
