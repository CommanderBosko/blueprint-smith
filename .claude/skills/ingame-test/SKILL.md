---
name: ingame-test
description: Hand a generated blueprint to the user for an in-game test (build, verify, copy to the clipboard, and say what to look at), then record the reported result in the project's docs. Use when the user says "test this in-game", "send me the blueprint", "copy the blueprint string", "I tested it in-game", or "record the in-game result".
---

# In-Game Test

Runs the in-game test round trip for one blueprint. Phase A hands it to the user ready to paste, with a list of what to check. Phase B writes what they saw back into `docs/techniques.md`, `CLAUDE.md` and `project-state.md`. (Bucket: Verification)

## Arguments

- **SPEC** (optional, Phase A): a spec path such as `examples/circuit_block.json`. With none, use the spec just built or discussed in this session. If that spec exists only in the conversation, write it to `<scratchpad>/<name>.json` first.
- Phase B takes no argument. It starts when the user reports back (often with a screenshot) and records the blueprint handed off in Phase A, or the one the user names.

## Steps

Run from the project root. Choose the phase from what the user said. "Test this in-game", "send me the blueprint" or "copy the blueprint string" means Phase A. "I tested it in-game" or "record the in-game result" means Phase B.

### Phase A: hand off

1. **Build, decode and copy:** `scripts/handoff.sh SPEC <scratchpad> [none|all]`. `<scratchpad>` is this session's scratchpad directory from the system prompt, never `$TMPDIR`. Omit the research argument: the CLI uses the research each spec type registers (`circuit_block`: all, the furnace columns: none). Pass `none` or `all` only to override it. The script runs `build SPEC --evaluate -o <scratchpad>/<spec-stem>.txt`, then `decode @FILE` (printing only a summary), then `wl-copy < FILE`. Branch on its exit code:
   - **0:** done. If the `HARNESS:` line says skipped (the build exited 3), the script fell back to a plain `build SPEC -o FILE`, so tell the user the harness verdict was skipped.
   - **1 or 2:** failed validation or the harness verdict (1), or a bad spec (2). Stop and report the failure lines from stderr. Don't hand off a failing blueprint.
   - **4:** built and decoded, but the clipboard copy failed. Give the user `! wl-copy < FILE` to run.
   - **5:** the string didn't decode. Stop and report it as a pipeline bug.

   Check that the `BLUEPRINT:`/`ENTITIES:` label and counts fit the spec. For example, the 24-furnace iron `smelting_column` should list 24 electric-furnace.
2. **Work out what to look at.** Read `docs/techniques.md` and list the entries this blueprint exercises: P (quality bar), F (game mechanics) and T (layout techniques). Start from the generator's T sections and the F facts they rely on. Flag entries still at **Prototype data**, **Inferred** or **Headless 2.0.77** only, because this test is their first chance in the user's game. For each entry, say concretely what to look for in-game, e.g. "both output lanes full", "the stub feeds the west lane" or "every furnace unloading, none blocked".
3. **Reply** with the `FILE:` path, `! wl-copy < FILE` for re-copying, the harness verdict (passed or skipped), the label and entity count, and the what-to-look-at list. Hand off one blueprint at a time, because each copy replaces the clipboard. Never put the string in the reply.

### Phase B: record the result

4. **Update the status of each exercised entry** in `docs/techniques.md`. P/F rows keep it in the table's Status cell, and T/H sections in their `**Status:**` line. Find each with `grep -n`, read the exact text, then edit it. Append, and never overwrite earlier confirmations:
   - Not yet seen in-game (Prototype data, Inferred, Headless): add "; confirmed in-game YYYY-MM-DD (<what was seen>)".
   - Already confirmed in-game: add "; again in the <blueprint>, YYYY-MM-DD (<what was seen>)", as F1 and F3 do.

   Use today's date (`date +%F`) and the user's words or what the screenshot shows. If the harness verdict ran, also note in H1 whether the game agreed with it.
5. **If the user reports a failure or teaches a correction,** add or update the technique entry and record how it was confirmed (e.g. "the user's screenshot, YYYY-MM-DD"). Then enforce it in code: an invariant in the generator's `check_flow` (or in `checks.py` if it's generic), plus a mutation test that breaks the layout on purpose and expects the build to fail. Run `.venv/bin/pytest -q -m "not harness"`, then `.venv/bin/pytest -q`. The project `CLAUDE.md` "Techniques Catalog" section requires this.
6. **Update the status docs.** Edit the generator's bullet under `## Status` in the project `CLAUDE.md` (e.g. "confirmed in-game YYYY-MM-DD", or what failed) and the matching line in `project-state.md`.
7. **On a pass, pin the layout** in `tests/fixtures/confirmed/` (`docs/techniques.md` checklist item 8):
   - If its spec already has a fixture, run `BPS_UPDATE_SNAPSHOTS=1 .venv/bin/pytest -q tests/test_confirmed.py` and update that fixture's `confirmed` line with the date and what was seen.
   - For a new block, first add a fixture with its `spec`, a `confirmed` line and `"entities": []`, then run the same command.
   - Then run `.venv/bin/pytest -q tests/test_confirmed.py` without the variable to check it passes.
8. **Report** each entry changed (old status, then new), any check and mutation test added with the test result, the two status-doc lines, and the snapshot pinned. Don't commit unless the user asks.

## Gotchas

- **`$TMPDIR` is unset here.** On 2026-10-11, `wl-paste > "$TMPDIR/old.bp"` expanded to `/old.bp` and failed. Always pass the session scratchpad's absolute path.
- **Never retype or paste the blueprint string into a reply.** On 2026-10-11 a hand-retyped steel string looped for minutes and came out corrupt (memory `feedback_blueprint-strings-via-clipboard.md`). Don't `cat` the file or dump `decode`'s JSON into context either. Hand over the file path and `! wl-copy < FILE`.

## Scripts

- `scripts/handoff.sh SPEC OUTDIR [none|all]` (step 1) builds with `--evaluate`, falling back to a static build when the harness exits 3. It writes `OUTDIR/<spec-stem>.txt` plus the build notes and verdict to `<spec-stem>.log`. It then decodes the string to a summary, copies it with `wl-copy` and reads it back. Output is `HARNESS:`, `BLUEPRINT:`, `ENTITIES:`, `FILE:` and `CLIPBOARD:` lines, never the string. Exit codes: 0 handed off, 1 failed validation or the verdict, 2 bad spec, 4 clipboard failed, 5 didn't decode, 64 usage.
