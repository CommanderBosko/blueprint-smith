## Session: 2026-10-13 — M2c scoped: the plant array for any machine

_Older entries are in [session-summary-archive.md](session-summary-archive.md)._

**Focus**: Resume and finish the scoping interview for generalising `plant_array`. The user asked for no building tonight.

### What changed (and why)
- **M2c brief** (`docs/m2c-brief.md`): `optimise` with just an item and a rate, for any non-fluid electric machine and any in-block intermediate made from one item. It keeps today's P > K < P layout, with 0 to 2 near items. Summarised in `PROJECT_BRIEF.md`'s v2 section.
- **Done test:** automation science at 240/s passes the harness and the user's in-game check. 7 proof requests (assembler 1 and 2, electric furnace, a mixed assembler/furnace row, the foundry, stone and steel furnaces) pass the harness at 4+ product machines a row, and every in-scope recipe builds statically.
- **`CLAUDE.md` Status:** points at M2c. The stale "commit and PR `v2-red-circuits`" line is fixed (it merged as PR #9).

### Decisions
- **Why M2c:** toward the v2 goal, more products without a generator per recipe.
- **Overrides:** the user went wider than two of my recommendations. The machines are any non-fluid electric machine, and the optimiser tries every qualifying intermediate, smelted ones included, so a pick may ask for ore. Footprint picks the machine.
- **Burners:** stone and steel furnaces only on request, never a default.
- **Regression:** the red and green blocks and their picks stay identical. The green pick stays `circuit_block`'s 11×11.
- **Deferred, not dropped:** "You're going to have to be ready for anything." Fluids, fission, fusion, Gleba, intermediates made from 2+ items and chains of them, arrays with no intermediate, 3+ near items, and a second layout are all required future milestones. M2c delivers a readiness table that maps each one to the code it would change.

### Issues / surprises
- **The review caught three wrong claims** in my first draft, each already settled in `docs/techniques.md`: foundry base productivity applies to belts (F21), beacons don't reach assembler 1 or burner furnaces (F24), and the harness hasn't matched every in-game result (the pre-T1 steel xfail).
- **It also found two code facts:** prod-3 is ejected from recipes that refuse productivity (F25), and `check_flow`'s `_roles` can't see furnaces, which carry no recipe (F13).
- **The first review hit the account's session limit,** and it ran again after the reset.
- **Secret scan** (project `/secret-scan`): clean across the tree and all 38 commits.

### Next session
- Write the M2c plan and get the user's OK before any code.

**Commits**: `912ec6b` plus this close (2 commits)

---

## Session: 2026-10-12 (close) — Optimiser, red circuit plant array, CI; next milestone picked

**Focus**: Catch the docs up to `main`. Several sessions since the last close were never closed, and the closing session itself changed no code.

### What changed (and why)
- **The optimiser (PR #7):** `blueprint-smith optimise` returns the smallest variant that passes the harness. For 240 green circuits/s it picks the compact 11×11 `copper: "north"` block, and that pick worked in-game.
- **Growth exemption (PR #8):** a machine that feeds only other machines can't jam anything, so it's no longer judged on output growth. Before, the check falsely failed 2 of 8 good variants.
- **M2b, red circuits (PR #9):** the generic `plant_array` hit 240.5/s in-game with both lanes full. It includes the user's three resource cuts and their mid-row lane reset (T12). Every blueprint now gets input display panels (P3) and an output lane balancer (P4).
- **CI (PR #10):** three jobs run on every push to `main` and every PR:
  - lint and the quick tests on GitHub's runners;
  - the full suite on a self-hosted runner, the user's gaming machine, because factorio.com refuses the server download from GitHub's runners.
  - Golden snapshots pin every in-game-confirmed layout. A skipped harness test fails the run.

### Decisions
- Runner jobs run as a sandboxed throwaway user that sees only a read-only server dir. A fork's PR can rewrite `ci.yml`, so an `if:` guard alone wouldn't keep it from running as the user. Fork PRs also need the user's approval.
- 1 output inserter a red plant is the default. With the lane reset it's enough in-game, and the growth bar now allows for the size of the inserter's hand.
- Next milestone (user): generalise `plant_array` to any machine and any in-block intermediate.

### Issues / surprises
- With HOME moved on the runner, the Lua-data test would have skipped, and the skip guard would then fail the run. It now finds the data beside `$BPS_FACTORIO_SERVER`.
- The scoping interview for the next milestone was paused before its first question wave.
- Secret scan (project `/secret-scan`): clean across the tree and all 36 commits.

### Next session
- Resume the `plant_array` interview at wave 1.
- With the user's OK, fix `CLAUDE.md`'s stale Status line ("commit and PR `v2-red-circuits`").

**Commits**: `e3383b3..6f24bcf` (21 commits, PRs #2–#10)

---

## Session: 2026-10-12 — M2 pieces A–E: harness, solver, checks, measured rates, circuit block

**Focus**: Build M2 up to the green circuit block, piece by piece: A, C and D in parallel, then B, then E.

### What changed (and why)
- **A, C, D (sub-agents in parallel):**
  - A: the harness feeds stacked belts by script (loaders can't stack), runs with all research, and applies the new machine bar.
  - C: `effects.py` models quality, modules, beacons and research. Its fit of 2.0's whole-percent rounding on the server matched 476 of 476 values.
  - D: new generic checks for modules, beacon reach, underground pairing and hidden entities, each confirmed against the server.
- **B:** micro-blueprints with script-fed machines measured one legendary stack inserter: 87.47/s from a stacked belt, 120/s plant to plant, 80/s onto a lane (2 fill it to 120). The solver matches the harness to 1e-6.
- **E:** `circuit_block`, the layout the user approved. A side-load stub fills the second output lane (T5). It makes 240/s in the harness, and the user confirmed it in-game: "It works perfectly".

### Decisions
- Power is never judged: the user's save has plenty (user).
- A machine that unloads only into other machines isn't judged on blocking: under direct insertion, spare capacity shows as blocked instead of idle (user).
- Copper input stacked like iron (user). Each piece gets its own stacked PR (user).
- B's rates are stored in `effects.py` and held to the harness by tests.

### Issues / surprises
- `products_finished` counts crafts (bonus crafts included), not items. It was recorded wrong yesterday; F18 is fixed.
- Inserters' pick-up and drop targets aren't set until they've run, so the mod reads where machines unload at the end of the window.
- The plan's 1% solver tolerance couldn't see the 2.0 rounding, so plant speed is held to 1e-6.
- Two cleanup commands were denied. The user deleted the leftover run dirs.
- Secret scan (project `/secret-scan`): clean across the tree and all 14 commits.

### Next session
- Merge PRs #2 → #3 → #4.
- Decide F's scope (tune one layout, or add a second first), then build the optimiser.

**Commits**: `e17499d..0c7c24c` (5 commits, on the stacked PR branches)

---

## Session: 2026-10-11 (afternoon) — Repo, lane balancing, steel_column, headless harness, M2 plan

**Focus**: Finish the smelting samples in-game, add steel from ore, then turn "an ML algorithm to optimise blueprints" into a scoped v2 and build its first milestone.

This close spans several sessions since the previous close, which ran before `git init`.

### What changed (and why)
- **Repo:** `git init` and a public MIT repo, `CommanderBosko/blueprint-smith`.
- **Spec bugs from probing edge cases:** a furnace accepted recipes it can't craft. The input-belt warning ignored ingredient amounts (steel at 4/s needs 20 plates/s). Malformed specs crashed instead of exiting 2.
- **Lane balancing (T1):** an inserter drops only onto a belt's far lane, so the old column filled one lane and blocked its last furnaces in-game. The user showed a layout with a west-priority splitter and a side-load every 2 furnaces. All 3 smelting samples then passed in-game at full belt. `docs/techniques.md` became the catalog of everything learned, and `CLAUDE.md` now requires reading it first.
- **`steel_column`:** the user wanted steel made from ore. Each iron furnace feeds the steel furnace beside it by direct insertion, at an exact 1:1 rate. It ran in-game with every furnace working. Adding it exposed a bug: `power_coverage` measured pole reach from the pole's edge instead of its centre.
- **v2 brief:** the interview and an independent review turned the ML request into a search-and-harness optimizer. ML is used only where it beats search or the solver. The confirmed brief is in the v2 section of `PROJECT_BRIEF.md`.
- **M1, the headless harness:** a Linux 2.0.77 headless server pastes, feeds, powers and measures a blueprint in about 6 s. It reproduces every in-game result except the pre-T1 steel jam.
- **M2 planned:** `docs/m2-plan.md`. One legendary electromagnetic plant with 2 beacons makes about 250 circuits/s, so the 240/s block is limited by inserters and belts.
- **Shipped:** PR #1 merged with a merge commit, and the feature branch deleted.
- **Secret scan:** this close added a `/secret-scan` skill and ran it. Tree and history are clean.

### Decisions
- The harness uses the Linux headless server, because the Steam copy is the Windows build under Proton.
- Amended P2: a harness failure fails the build.
- Output is judged on what the machines crafted. Two extra failures: a machine whose output backs up, and output that never reaches the belt end.
- The harness assumes no research by default; with everything researched, steel productivity research adds 10%.
- M2 machine bar (user): fail only when blocked on output, because beacon steps make exact sizing impossible.

### Issues / surprises
- A blueprint string retyped by hand into a reply looped and came out corrupted. Strings now go out only as file paths or `wl-copy` commands.
- The pre-T1 steel jam seen in-game doesn't reproduce in the harness (strict xfail).
- Loaders can't output stacked items, so M2's harness has to feed stacked belts by script.
- The transcript scan was misleading at first: piping it through `head -c` cut it off, and a relative project path made it fall back to one transcript.

### Next session
- M2 pieces A (harness), C (solver) and D (checks) in parallel, then B, E and F.
- In-game, for the user: re-check copper 30/s for blocked bottom furnaces, and run 2 more `steel_column` samples.

**Commits**: `9a03f8a..c0d4def` (8 commits, including the PR #1 merge)

---

## Session: 2026-10-11 — First in-game test; pole wiring fix

**Focus**: Import the smelting column in-game and fix what broke.

### What changed (and why)
- The first in-game import worked: the column builds, belts flow south, and the inserters move ore → furnace → plate belt. But 11 of 12 poles had no power.
- The cause was missing copper wires, not spacing (6 tiles apart, reach 9 per `entities.lua`). A pasted blueprint only keeps the wires it carries, so the game doesn't join poles inside one. The pipeline now calls `generate_power_connections(only_axis=True)` (a ladder: 16 wires for 12 poles). The new generic check `pole_network` fails any build with an unwired pole or a wire past reach. 3 new tests, 19 passing.
- Re-imported the fixed string in-game: fully wired, everything powered.

### Decisions
- Wire in the pipeline (works for every generator) rather than per generator. Axis-only wiring keeps the grid tidy, and `pole_network` catches any pole that leaves out.

### Issues / surprises
- Our checks tested pole *coverage* but never pole-to-pole *wiring*, so the gap only showed up in-game.
- The user asked to commit at the end, but the project still isn't a git repo. Paused before `git init`, at the user's request.

### Next session
- `git init -b main` and a first commit (asked for, not done yet).
- 2 more in-game sample specs for `smelting_column`, then pick the next generator.

**Commits**: none (not a git repo yet)

---

