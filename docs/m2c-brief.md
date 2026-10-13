# Project Brief: M2c, a plant array for any machine and any one-item intermediate

*Interviewed 2026-10-12/13. Every key decision below was confirmed explicitly by the user, and the brief was revised after an independent review. It amends the v2 section of `PROJECT_BRIEF.md`.*

## Goal
Generalise `plant_array` along two axes:
- **the machine:** any non-fluid electric machine, and on request a burner furnace;
- **the in-block intermediate:** anything made from one item.

Then `blueprint-smith optimise` with just an item and a rate covers every recipe in that scope, without a hand-written generator per recipe. This moves toward the v2 goal: plain-word requests for any product.

## Problem it solves
`plant_array` is generic in name only:
- `INTERMEDIATES` holds two recipes (red and green circuits).
- The machine is the electromagnetic plant.
- Its 4×4 size is built into the row, beacon band, hand-off and mirror constants.
- `check_flow` only recognises assemblers by their recipe (`_roles`).

Any other product needs new code.

## Target users
Just the author.

## Must-haves
- **Requests:** `{"item": ..., "rate": ...}` is enough. A request may override the machine, the intermediate and quality. The other defaults stay: legendary machines, modules and beacons, speed-3 in beacons, everything researched.
  - **Machine:** the optimiser tries each capable electric machine, and footprint picks, with power as the tie-break (v2's rule). Never a burner by default.
  - **In-block intermediate:** the optimiser tries every ingredient that qualifies, smelted ones included, and footprint picks. So a pick may ask for ore instead of plates, and its report names the input belts it needs.
  - **Machine modules:** prod-3 in every slot, or speed-3 when the recipe refuses productivity (F25: prod modules are ejected).
- **Machines:** assembler 1, 2 and 3, the EM plant, the electric furnace, and the foundry for its fluid-free recipes (belts). Stone and steel furnaces only when a request asks.
  - Size, module slots, base productivity and whether beacons reach the machine all come from prototype data. Under F24, assembler 1 and the burner furnaces take no beacon effects.
- **Fuel:** when burner furnaces are requested, fuel reaches every burner machine as one more belt input.
- **Mixed rows:** the product machine (P) and the intermediate machine (K) may be different machines and sizes, for example low density structures in assembler 3s with steel smelted in electric furnaces beside them.
- **Intermediates:** one in-block intermediate made from one item (cable, gears, pipe, iron sticks, steel, iron or copper plate), handed over by direct insertion in today's P > K < P layout.
- **Near items:** 0 to 2, one per lane of the near belt. With 0, a furnace can make steel from ore, as `steel_column` does.
- **`check_flow` sees every machine:** furnaces carry no recipe (F13), so roles can't come from `e.recipe` alone.
- **Comparison report:** for the science pick and each proof request, the footprint, the K count, and each K's use (items consumed ÷ the solver's capacity, since under direct insertion a K's spare capacity reads `full_output`, P2). It also gives an estimated footprint for a layout where one K feeds many P's, sized from the solver's K count. The user decides from it whether that second layout is the next milestone.
- **Readiness table:** maps each deferred item (below) to the code that would change and how. It flags anything that would need a rewrite rather than an extension (for example `Recipe.far` holds one item). The user signs it off at the end.
- The techniques catalog (`docs/techniques.md`) gets every new technique and fact, each with a check and a mutation test (CLAUDE.md).

## Deferred: future milestones, each required eventually
(User: "You're going to have to be ready for anything.")
- Fluids, fission and fusion.
- Gleba and biochambers. This amends v2's "until the Nauvis types work" line: they're now a required future milestone.
- Intermediates made from 2+ items, and chains of intermediates.
- Arrays with no intermediate.
- 3+ near items.
- A second layout, if the comparison favours one. This is the next milestone, not this one.

## Out of scope
- Replacing `circuit_block`, `smelting_column` or `steel_column` with `plant_array`.
- Mods. Loading them stays the v2 stretch goal.
- Everything already out of v2: RCON or the live game, city blocks, chain-to-raw requests.

## Constraints
- Python, the existing pipeline and harness. draftsman stays below 4. Factorio 2.0.77 + Space Age, headless Linux server.
- **Regression:**
  - The existing confirmed fixtures in `tests/fixtures/confirmed/` stay unchanged, so the red and green blocks stay identical entity for entity.
  - The red pick doesn't change.
  - The green pick stays `circuit_block`'s 11×11 north layout, even if a `plant_array` green block would be smaller.
  - A science fixture is added once the in-game check passes.
- The full suite and CI (lint, quick, the self-hosted harness job) stay green.
- No deadline.

## Definition of done
1. **Science:** `blueprint-smith optimise '{"item": "automation-science-pack", "rate": 240}'` returns a plant-array blueprint that passes the harness. The bar is at least 98% of 240/s, both output lanes full, no machine failing the machine bar, with everything researched and the legendary defaults. Whichever intermediate wins counts. (Solver: 16.1/s per assembler 3 with 4 beacons, so about 15 assemblers. With gears in-block, a gear assembler makes 83/s with 1 beacon.)
2. **In-game:** the user's check of the science pick agrees with the harness.
3. **Proof requests:** each one passes the harness at a rate that needs at least 4 product machines a row, under M2's bar (at least 98% of its rate, the machine bar). The plan gives each request's exact rate and overrides.

   | Request | P | K (in-block) | Covers |
   |---|---|---|---|
   | automation science | assembler 1 | assembler 1 (gears) | no slots, no beacons |
   | automation science | assembler 2 | assembler 2 (gears) | 2 slots |
   | steel from ore | electric furnace | electric furnace (iron plate) | 0 near items, furnace roles |
   | low density structures | assembler 3 | electric furnace (steel) | mixed row, same size |
   | transport belts | foundry | assembler 3 (gears) | mixed sizes, 5×5, speed-3 fallback |
   | steel from ore, by override | stone furnace | stone furnace (iron plate) | burners, fuel |
   | steel from ore, by override | steel furnace | steel furnace (iron plate) | burners, fuel |

   The EM plant is covered by the red block.
4. **Coverage:** a test builds a block for every recipe in scope, at a rate the plan sets, and each one passes the static checks. In scope means a one-item intermediate, 0 to 2 near items, and a capable non-fluid electric machine.
5. **Regression:** the regression bar above holds.
6. **Report and readiness:** the comparison report and the readiness table are delivered, the user has decided on the second layout, and the user has signed off the table.

## Open questions / risks
- **Geometry is the main engineering risk.**
  - Machines run 2×2 (stone and steel furnaces), 3×3, 4×4 (EM plant) and 5×5 (foundry), and rows may mix sizes.
  - Beacon reach (F24), inserter edges, hand-off gaps, poles and the mirror line all change with size.
  - Blocks for machines that beacons can't reach need no beacon band at all.
  - All of this while the red block stays identical. The snapshots catch any drift.
- **Fuel paths:** today a K takes only from the far belt, so the plan must say how fuel reaches the burner furnace Ks and Ps (for example on the far belt's second lane, or on the near belt when there are 0 near items).
- **Foundry productivity:** its +50% base productivity applies even to belts, which refuse productivity modules (F21). The solver must apply it there.
- **Measured rates:** the inserter rates F28–F30 were measured into and out of EM plants. Other machines and items (gears, ore, fuel, furnaces) may need new measurements before the sizing can be trusted.
- **Calibration:** only the science block is checked in-game. The harness has matched every in-game result except the pre-T1 steel jam (still a strict xfail), and only for furnaces and EM plants.
- **Search cost:** machines × intermediates × counts make many more variants. At about 6 s a run, the optimiser's run cap and batching may need tuning.
