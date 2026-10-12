# M2b plan: red circuits on a generic plant array

The next milestone after M2 (`PROJECT_BRIEF.md`, v2 section, M2b). Scoped with the user 2026-10-12. Branch `v2-red-circuits`.
- **Request:** "fill a turbo belt of red circuits", i.e. 240/s stacked. The bar and defaults are M2's: legendary EM plants with legendary productivity-3, legendary beacons with legendary speed-3, everything researched.
- **Inputs:** green circuits, plastic and copper plates, each on its own stacked turbo belt at the block's edge. The block makes its own copper cable.
- **Generator:** generic. A beaconed array of plants parametrised by recipe, with an optional in-block intermediate handed over by direct insertion. Red circuits are the first recipe and the done test.

## Numbers (solver, `effects.py`)

A red circuit takes 2 green, 2 plastic and 4 cable over 6 s. A plant makes +175% (base +50% plus 5 legendary prod-3), with the cap at +300%. Nothing researches red circuit productivity.

| Beacons per plant | Red/s per plant | Green and plastic/s in, each | Cable/s in |
|---|---|---|---|
| 3 | 25.37 | 18.45 | 36.9 |
| 4 | 29.22 | 21.25 | 42.5 |
| 5 | 32.61 | 23.72 | 47.43 |

- **240/s needs** 87.27 crafts/s: 174.5 green/s, 174.5 plastic/s and 349 cable/s. The cable takes 63.5 copper/s.
- **A cable plant is never the limit.** With 1 beacon it makes 357 cable/s, with 4 it makes 701. One cable plant feeds the red plants on both sides of it.
- **Green alone exceeds a lane.** 174.5/s doesn't fit on one lane (120/s stacked), so a single row can't be fed from one mixed green|plastic belt. That's why there are two rows.

## Layout (approved by the user 2026-10-12)

```
 rows  band          (one row of plants shown; row B is the mirror image below the beacons)
  1    Cu    ══════════════════════════════   reached only by the long-handed inserters
  1    G|P   ══════════════════════════════   green lane | plastic lane, merged at the west edge (F3)
  1    ins      i   LL    i  i   LL    i      i: stack inserter G|P→R   L: long-handed Cu→K
  4    row A   [R1]>[K1]<[R2][R3]>[K2]<[R4]   each cable plant hands cable to the red plant on either side
  1    ins       o         o  o         o
  1    Out A ══════════════════════════════╗  row A fills its south lane (F1)
  3    beacons BBBBBBBBBBBBBBBBBBBBBBBBBBBB ║  one shared beacon row, 2 tiles from both rows: 4 per plant (F24)
  1    Out B ══════════════════════════════╬═▶ Out A crosses under Out B and side-loads its south lane
 ...   row B mirrored (its plants fill Out B's north lane)          ≈ 35 × 21 tiles
```

**Why this shape:**
- **Each plant can only reach two belts.** A plant in a row has a belt on each long side, and its short sides face its neighbours. A red plant needs a mixed input belt and an output belt, so its cable has to come from a cable plant beside it. That cable plant still needs copper, and the only free belt is one row further out, so it uses long-handed inserters reaching over the green|plastic belt.
- **Beacons fit on only one side of each row.** A beacon reaches across at most 2 tiles of gap (F24). The input side is 3 rows deep (Cu, G|P, inserters), so the beacons go on the output side, and both rows share that one beacon row.
- **The two outputs fill the same lane.** Each row's plants drop onto the far lane of their own belt (F1), and in both rows that's the lane next to the beacons. So Out A has to reach Out B's other lane: it crosses under Out B and side-loads it from the south (F3).

**The west front end:** each input belt is split in two (one half per row). Each row's G|P belt gets green side-loaded from one side and plastic from the other (F3). The exact tiles get drawn in the generator's docstring before the in-game test.

**Sizing at 240/s:** 4 red plants per row. With 4 beacons each, a row makes 116.9/s, which is under 98% of a 120/s lane. So one plant per row gets a 5th beacon, which brings the row to 120.3/s. Two cable plants per row.

## Work breakdown

| Piece | Files | Delivers | Depends on |
|---|---|---|---|
| **A. Measured primitives** | `tests/test_harness_primitives.py`, `effects.py` (a measured-rate constant), techniques entries | Legendary long-handed inserter, stacked turbo belt → plant (copper into a cable plant), measured like F28. A legendary stack inserter taking from a mixed green\|plastic stacked belt into a red plant. Both repeated across 2 runs. | — |
| **B. Generator** | `generators/plant_array.py` (+ shared helpers moved out of `circuit_block.py`), `tests/test_plant_array.py` | The layout above, parametrised by recipe, intermediate, plants per row and beacons. Ports, `check_flow` with a mutation test per technique, `sizing`, notes and `variants`. | A's rates set the defaults (a placeholder until then) |
| **C. Harness and optimiser** | `optimise.py` if needed, harness tests | The default red block passes the harness. `blueprint-smith optimise` on the red request picks a passing variant. | A, B |
| **D. In-game** | docs | The user's spot-check of the pick, recorded in `docs/techniques.md`. | C |

A and B run in parallel: A by a sub-agent, and B by the main session, since its geometry is one tightly coupled design. C and D follow.

## Progress

**A, 2026-10-12** (sub-agent):
- **Long-handed (F29):** a legendary long-handed inserter moves 13.33/s from a full stacked belt 2 tiles out, and two add up. So each cable plant gets 2.
- **Mixed belt (F30):** a stack inserter takes 87.47/s from a green|plastic belt, the same as from a one-item belt. So each red plant gets 1.
- Both rates repeated exactly across 2 runs.

**B and C, 2026-10-12** (main session; 34 tests in `tests/test_plant_array.py`):
- **`plant_array`:** built as drawn in its docstring. It's 42×21 for 4 red plants and 2 cable plants a row.
  - The band's west beacon sits over the front end's risers, which hop under it. An in-row east beacon gives each row's last red plant a 5th. So the beacons are 4, 4, 4, 5 a row: 120.27/s against the 120/s lane.
  - Medium poles sit in the inserter rows.
  - It's generic over the recipe. Green circuits build too: one near item, iron.
- **First harness run:** 97.2% with 1 output inserter a plant. The row's last plants found too few free slots in their filling lane. With 2 a plant it passed: **237.80/s (99.1%), lanes 119.07/118.67**, and no red plant blocked over 1.3%.
  - Recorded as T7. The sizing now models it, as each plant's free share of the lane.
- **`blueprint-smith optimise` on `{"item": "advanced-circuit", "rate": 240}`:** 12 variants, all 4 a row with the east beacon and 2 output inserters. It picked the fewest inserters (near 1, hand-off 1, long-handed 2, output 2) in 28 s.
- **New techniques:** T7 (more output inserters down a filling lane), T8 (two items on one belt), T9 (merging two rows' outputs) and T10 (long-handed reach for the cable plant). Each has a mutation test.
- **Input labels (P3), 2026-10-12:** at the user's request, before the in-game check, every generator's inputs now get a display panel showing their item, 2 tiles west of the red block's input belts. The block's ports, footprint and harness result are unchanged.
- **The user's in-game copy, 2026-10-12:** they built it, cut resources in a couple of places, and added a lane balancer at the output (screenshots).
  - The balancer is now a rule for every generator (P4, T11): the pipeline adds one after every belt output, and the red block passes the harness with it.
  - Their blueprint string, compared tile by tile against the pick, showed three changes:
    - The copper feed for row B hops under both near items' belts in one go, instead of each going under it (2 undergrounds fewer).
    - Row B's near items merge as soon as they surface from under the beacon row (T8), with one belt down to the row (5 belts fewer).
    - Both outputs turn in past the band's end and side-load a middle belt (T9), with no undergrounds (2 fewer).
  - All three are now in the generator, and the generated block matches theirs exactly: 325 of 325 entities, apart from their test loaders. With the balancer the harness gives 238.09/s (99.2%), lanes 119.00/119.07. It has 8 undergrounds where the pick had 12, and 223 belts, 6 of them the balancer's.
**D, 2026-10-12:** the regenerated block with the user's changes ran in-game: "It shows 240.5/s with both lanes full. The balancer works. The display panels are placed perfectly."
- The Rate Calculator's 240.5/s is the solver's 2 × 120.27, and its 174.9/s green and plastic match +175% productivity.
- The harness (238.09/s delivered) agreed. **M2b is done.**

**The lane reset, 2026-10-12 (after D):** the user saw the red plants' output inserters waiting on a full lane in-game, and added T1's priority splitter and side-load halfway along each output belt.
- Their exported blueprint diffed to just that change, and the generator now matches it entity for entity (T12).
- Harness: 240.55/s crafted, 240.00/s delivered, lanes 120.00/120.00, and no red plant blocked (before: 238.09/s, 1.1%).
- With 1 output inserter a plant it also makes 240/s with full lanes, but the harness failed one plant on 4 items of output growth.
- The user confirmed 1 a plant works in-game, and over 6× the window the growth stayed at 4–7 items, never building: a stack inserter's 16-item hand swinging. The growth bar now allows for the biggest hand unloading a machine (P2).
- `sizing` credits the reset, and `optimise` now picks 1 output inserter a plant: 313.85 MW against 320.58 MW, and 8 stack inserters fewer.

## Risks

- **Oversized rows block.** If a row makes more than its lane takes, the extra shows up as red plants blocked on output. The machine bar fails a plant that's blocked for more than 5% of the window, so each row has to land between 98% and 105% of a lane. If the harness says that window can't be hit, the bar comes back to the user.
- **Long-handed inserters are slow.** A cable plant needs about 15.5 copper/s. If one long-handed inserter can't manage half of that, the cable plant's top edge (4 tiles) still has room for more.
- **The last plant in a row has to find gaps in a nearly full lane.** Still an open question from T1. The harness decides.
- **Inputs are fed full.** Each input port is fed at 240/s but only part of it is eaten (green and plastic 174.5/s, copper 63.5/s), so input belts back up. That's normal for a block, and the harness already measures the output side only.

## Verification plan

1. **Baseline:** `.venv/bin/pytest -q` is green before the work starts.
2. **A:** each measured rate repeats within 2% across 2 runs, and is recorded in `docs/techniques.md` as "Headless 2.0.77".
3. **B, static:** `.venv/bin/pytest -q tests/test_plant_array.py`. Ports sit on open belt ends; every generic check passes; `check_flow` holds the flow, lanes, merge and front end; and each technique has a mutation test that breaks the layout and expects the build to fail. `blueprint-smith build` on the default spec exits 0.
4. **C, harness:** the default red block delivers at least 98% of 240/s, both lanes about 120/s, and nothing fails the machine bar. `blueprint-smith optimise '{"item": "advanced-circuit", "rate": 240}'` returns a pass. The full suite is green, and `circuit_block`'s optimiser pick is unchanged.
5. **D, human:** the user imports the pick in-game and confirms 240/s with both lanes full.
