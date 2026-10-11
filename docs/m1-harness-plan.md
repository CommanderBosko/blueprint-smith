# M1 plan: headless evaluation harness

**Status (2026-10-11):**
- S0 and slices A, B, C and D are done. The harness is calibrated: `tests/test_harness_calibration.py` gives 17 passed and 1 strict xfail.
- **M1 is not fully done.** Two open items remain:
  - The pre-T1 steel jam seen in-game doesn't reproduce in the harness.
  - The user's in-game re-check of the copper 30/s bottom furnaces is still pending.
- Both are listed under "Open questions" in `docs/techniques.md`.
- What changed from the plan below:
  - **Research defaults to none (F14).** The plan had everything researched, which put steel productivity +10% into every result.
  - **The output bar uses the crafted rate** (finished crafts plus progress) rather than items counted at the sink.
  - **Two more failure checks:** output-buffer growth (F15) and delivery below 80%.
  - **The window scales with craft time** (approved by the user).

Milestone 1 of the v2 optimizer (`PROJECT_BRIEF.md`, v2 section). Researched 2026-10-11. The harness runs a blueprint in a real headless Factorio 2.0.77 + Space Age, measures it, and turns the result into a pass/fail verdict, so the user no longer has to test every blueprint in-game.

## Research findings

**Runtime**
- The Steam install is the Windows build under Proton, so it can't be used headless here.
- The host is NixOS 26.11, with nix-ld and steam-run installed and `allowUnfree` on.
- The 2.0.77 headless server is available in two ways:
  - `https://factorio.com/get-download/2.0.77/headless/linux64`: a 57 MB `.tar.xz`, no login needed.
  - nixpkgs `factorio-headless`, currently at 2.0.77.
- Space Age, quality and elevated-rails ship with the headless server and are enabled by default.

**Run flow**
- The Lua API has no way to quit the game, so the run uses the benchmark flags:
  - `--create save.zip` runs every mod's `on_init`.
  - `--benchmark save.zip --benchmark-ticks N` runs control.lua (including `on_tick` and `helpers.write_file`) with no 60 UPS cap, then exits. A published benchmark ran about 2,500 UPS.
- Two instances can't share a write-data dir because of its lock file. Each run gets its own `-c config.ini` with `[path] write-data=<tmp>`.
- Runtime Lua can't read arbitrary files. The blueprint goes in as a generated `job.lua` inside the harness mod, which `control.lua` loads with `require`.
- `--until-tick` is ignored on headless. Don't use it.

**Lua API** (local `doc-html/`, version-matched)
- **Building the blueprint:**
  - `game.create_inventory(1)`, then `import_stack(str)`, then `build_blueprint{surface, force, position, build_mode}`. That returns ghosts, which `silent_revive()` turns into real entities.
  - `silent_revive()` returns the revived entity and an item-request-proxy for any modules. Fulfil the proxy by inserting into the module inventory, then destroy it.
  - `create_entities_from_blueprint_string` works only in simulations, so don't use it.
- **Clean surface:**
  - `game.create_surface` with `no_enemies_mode`, then `generate_with_lab_tiles`.
  - Turn off `game.map_settings.pollution` and enemy expansion and evolution.
  - On the force: `research_all_technologies()`, `enable_all_recipes()` and `unlock_quality()`.
- **Feeding and sinking:**
  - The hidden prototypes `loader`, `fast-loader`, `express-loader` and `turbo-loader` (15/30/45/60 per s) can be placed by script.
  - Use `infinity-chest` with `set_infinity_container_filter` for inputs and a plain chest for the output sink.
- **Power:** the hidden `electric-energy-interface` (2x2). Wire it with `get_wire_connector(defines.wire_connector_id.pole_copper, true):connect_to(...)`.
- **Measuring:**
  - Read `entity.status` (`defines.entity_status`):
    - Working: `working`, `normal`.
    - Starved: `no_ingredients`, `item_ingredient_shortage`.
    - Output blocked: `full_output`.
    - Power: `no_power`, `low_power`.
  - Per-lane belt flow comes from `get_transport_line(...)`. `get_detailed_contents()` gives each item a `unique_id`, so items crossing a tile can be counted per lane.

**Prior art to borrow from**
- FactorioTest (MIT): the per-run config.ini and benchmark-as-runner pattern.
- BELT and belt-sanitizer (MIT): stamping a blueprint and measuring production. They target 2.1, so we borrow the logic rather than use them directly.

## Spike results (S0, 2026-10-11)

The code is in `spike/harness/` (`mod/control.lua`, `run.py`). Run it as `.venv/bin/python spike/harness/run.py BP INX,INY OUTX,OUTY IN_ITEM OUT_ITEM BELT [warmup] [window] [tmpdir]`.

**Runtime**
- The tarball server at `~/.cache/blueprint-smith/factorio-headless-2.0.77/factorio/bin/x64/factorio` runs directly under nix-ld and reports `2.0.77 (build 84539, linux64, headless)`.
- The headless build has no `--disable-audio` flag. Passing it prints the help text and exits with 1.
- Wall-clock time: `--create` takes 1.7 s. A benchmark of 10,800 ticks (3 game minutes) takes 3.5 s and 21,600 ticks take 6.1 s, about 4,000 UPS on a 252-entity column.

**Building**
- `import_stack` works on an empty `game.create_inventory(1)` slot.
- `build_blueprint{position={0,0}, build_mode=forced}` centres the blueprint. Use the floor of the smallest `bounding_box.left_top` over the revived entities as the origin.
- A build done in `on_init` during `--create` survives into `--benchmark`.
- `silent_revive` keeps the splitter `output_priority` (`right` × 12). The blueprint's copper wires become real wires on all 24 poles.

**Loaders**
- `direction` is the port's flow direction in both cases.
- To feed, use `type="output"` with the infinity chest upstream. To sink, use `type="input"` with the chest downstream.
- Call `update_connections()`, then check that `loader_container.unit_number == chest.unit_number`. Comparing entities with `==` does not work here.

**Power**
- The energy interface's `power_production` is in J/tick: 8.33e9 means 500 GW.
- The harness pole auto-connects when created, so `connect_to` can return false even though the pole is linked. Check `electric_network_id` against the blueprint's poles instead.

**Measured, iron 15/s sample (warmup 7200, window 3600)**
- Output 15.0/s, lanes 7.57 and 7.55/s, all 24 furnaces working 100% of ticks.
- This matches the in-game result.
- The lane counts run slightly high because items already on the tile when the window opens get counted. Seed the previously seen IDs at tick W−1.

**Measured, pre-T1 steel (`f1d113a`)**
- The output ramps up for about 110 s. A 120 s warmup is too short for a 16 s recipe.
- The furnaces craft in sync, which makes the output bursty: 10 s buckets read 2.9 to 4.0/s, so a 60 s window lands about ±5% off.
- Every furnace stays at ≥0.987 working with a free-draining sink. **This does not reproduce the in-game blocking.** It needs resolving with the user: was the in-game output drained, or does a mod change the behaviour?

## Contract (fixed before the slices fan out)

**Ports.** Each generator returns ports alongside its entities and notes. `BuildResult.ports` carries them.

```python
@dataclass(frozen=True)
class Port:
    role: str          # "input" | "output"
    item: str          # e.g. "iron-ore"
    belt: str          # belt prototype at the port, sets the loader tier
    tile: tuple[int, int]  # the belt tile at the edge: first tile of an input belt, last tile of an output belt
    direction: int     # flow direction of that belt (N=0 E=4 S=8 W=12)
    rate: float        # input: informational (fed at full belt rate); output: the target items/s
```

`tile` is relative to the blueprint's bounding-box top-left, meaning the minimum tile over all entities. The harness finds the same corner after building, so it doesn't depend on how the game positions a pasted blueprint.

**Job** (`job.lua`, generated by Python): `return { blueprint = "0e...", ports = {...}, warmup_ticks = W, window_ticks = 3600 }`.

**Result** (`script-output/bps-result.json`, written by the harness mod on its last tick):

```json
{
  "version": 1,
  "build": {"ghosts_left": 0, "proxies_left": 0, "errors": []},
  "ticks": {"warmup": 7200, "window": 3600},
  "outputs": [{"item": "iron-plate", "count": 900, "rate": 15.0, "lane_rates": [7.5, 7.5]}],
  "machines": [{"name": "electric-furnace", "position": [3.5, 1.5], "working": 1.0, "statuses": {"working": 3600}}],
  "power": {"unpowered_machine_ticks": 0}
}
```

**Verdict** (Python):
- The run fails if any of these holds:
  - The build is incomplete (`ghosts_left`, `proxies_left` or `errors`).
  - Any output's `rate` is below 98% of its port's target.
  - Any machine's `working` share is below 0.95.
- Lane rates and power are reported in the summary.
- A failure raises `BuildError`, which makes the CLI exit with 1 (the amended P2).

**Steady state:** `warmup_ticks` = max(2 game minutes, 3 × the longest belt's transit time). The spike checks this by comparing two back-to-back windows.

## Work breakdown

**S0: spike (serial, blocks A and B).** Get the server running and push one blueprint (the iron 15/s sample) through a throwaway mod using create, then benchmark, then a result file. Resolve the open questions:
- Does `import_stack` work on an empty script-inventory slot?
- Does a build done in `on_init` during `--create` survive into the benchmark?
- Does revive keep the splitter priority, and do its copper wires become real?
- How should a loader be oriented and placed?
- What units does the energy interface's power setting use?
- What is the wall-clock time per 1,000 ticks?

The spike's code lives in `spike/`.

**Then three parallel slices**, each a sub-agent with a strict file boundary, built against the contract above:

| Slice | Files it owns | Delivers |
|---|---|---|
| A: harness mod (Lua) | `src/blueprint_smith/harness/mod/` (`info.json`, `control.lua`) | Builds the surface, pastes and revives the blueprint, fulfils module proxies, places loaders, chests and power, measures, writes the result JSON |
| B: runner (Python) | `src/blueprint_smith/harness/{__init__,server,runner,verdict}.py`, `tests/test_harness_runner.py` | Finds and provisions the server and checks it is 2.0.77; per-run temp dir, config.ini and mod-list; writes `job.lua`; runs create then benchmark; parses the result; verdict with thresholds |
| C: ports | `generators/{__init__,columns,smelting_column,steel_column}.py`, `pipeline.py`, `tests/test_smelting_column.py`, `tests/test_steel_column.py` | Generators return ports; `BuildResult.ports`; tests that ports sit on the belt ends; a mutation test |

C needs no spike results and can start alongside S0.

**D: integration (me, after A, B and C).**
- A `blueprint-smith evaluate SPEC` CLI command, plus `build --evaluate`.
- Calibration fixtures for the three failure layouts:
  - `tests/fixtures/`: the pre-T1 copper and steel strings frozen from `f1d113a`, with their ports.
  - The unwired variant, built with wiring skipped.
- `tests/test_harness_calibration.py`.
- Recording the time per run.
- `docs/techniques.md` entries for the harness and the P2 status.

## Verification plan

1. **Baseline:** `.venv/bin/pytest -q` is green before any change (73 tests).
2. **S0:** the spike's result JSON shows the iron sample producing plates on both lanes with every furnace working, and the wall-clock time per run is noted. It only has to prove the loop works; calibration comes in D.
3. **Slices**, each running its own tests plus the full suite:
   - A: run the mod against the iron sample through B's runner, or the spike runner if B isn't merged yet.
   - B: unit tests for config.ini and mod-list generation, `job.lua` escaping, result parsing, and the thresholds. 97.9% must fail and 98.0% pass; a machine at 0.949 must fail.
   - C: every existing test still passes. New tests check port tiles against the belt ends. A mutation test puts a port off the belt and expects a failure.
4. **Calibration, D:** `.venv/bin/pytest -q tests/test_harness_calibration.py` against the real server. Skipped when no server is found.

   | Case | Expected verdict |
   |---|---|
   | Iron 15/s | Pass, both lanes ≥ 7.35/s |
   | Steel 3/s from plates | Pass |
   | Steel 3/s from ore (`steel_column`) | Pass, every furnace ≥ 0.95 |
   | Copper 30/s | Pass. Counts as ground truth only after the user re-checks the bottom furnaces in-game |
   | Pre-T1 copper, 24 furnaces, target a full red belt | Fail: about 15/s, one lane |
   | Pre-T1 steel, 24 furnaces | Fail: the bottom furnaces fall below 0.95, `full_output` |
   | Unwired poles | Fail: `no_power` |
   | Every case run twice | Same verdict, output within 1% |

5. **CLI end to end:**
   - `.venv/bin/blueprint-smith evaluate examples/smelting_column.json` exits 0 and prints a summary.
   - The unwired fixture exits 1.
6. **Human step:** the user re-checks copper 30/s in-game for blocked bottom furnaces. That is the only in-game test M1 needs.
