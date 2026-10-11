---
name: secret-scan
description: Triggers when the user says "secret scan", "scan for secrets", "check for leaked secrets", "is it safe to push", "any secrets in the repo", or "pre-public check". Read-only scan of the working tree and full git history for plaintext secrets, tuned to this project's no-secrets (public repo, nothing credentialed) setup.
model: haiku
version: 0.1.0
---

# Secret Scan

A read-only guard that scans the **working tree and full git history** for plaintext
secrets before a push or before changing repo visibility.

## Arguments

None.

## What it knows about this project

- **Secret-management scheme:** none. blueprint-smith is a public MIT repo
  (`CommanderBosko/blueprint-smith`) whose code needs no credentials: the headless
  Factorio server it downloads needs no login, and nothing reads an API key. Any secret
  in the tree is a leak by definition. `.env` is gitignored as a safety net.
- **Encrypted/managed secret locations:** none. There is no sops, git-crypt or vault
  setup, so the encrypted-secret integrity pass is skipped.
- **Paths excluded from pattern matching:** only `.claude/skills/` (this skill's own docs
  and script contain example secret patterns). Everything else is scanned, including
  blueprint strings.
- **Known intentional non-secrets (don't flag these):** Factorio blueprint strings, which
  are long base64 (zlib) runs starting with `0e`. They appear in `examples/`,
  `tests/fixtures/harness/`, `spike/harness/*.bp` and sometimes in docs. They are public
  game data, not credentials. If one ever matches a pattern by chance, confirm it's
  inside a blueprint string and treat it as a false positive.
- **Full git-history scan:** yes. The repo is small (7 commits, about 1.3 MB of `.git` as
  of 2026-10-11) and public, so every commit is scanned.

## Instructions

1. Run `scripts/secret-scan.sh`. It performs four passes:
   - **Working tree** — high-signal patterns (private-key blocks, password hashes,
     GitHub/AWS/Slack tokens, plus Discord webhook URLs, Anthropic API keys and Factorio
     service tokens) across tracked files, excluding the configured paths.
   - **Encrypted-secret integrity** — skipped: this project has no encrypted-secret
     scheme, so the script prints a skip line here. That is expected, not a failure.
   - **Git history** — the same high-signal patterns across *all commits* (catches
     secrets that were committed then removed but still live in history). Prints
     `commit:path` hits. History scanning is on for this project; every commit is checked.
   - **.gitignore coverage** — informational check that common secret-file extensions
     are ignored.

2. Report the result. If **clean**, say so plainly. If there are findings, present each
   with its location and the right remediation:
   - **Plaintext secret in the working tree** → delete it from the file and keep it out
     of the repo entirely (a local, gitignored `.env` or the tool's own config dir, e.g.
     `~/.factorio/player-data.json`). Rotate the credential if the file was ever pushed:
     the repo is public.
   - **Unencrypted managed-secret file** → not applicable here: this project has no
     encrypted-secret scheme, so this finding can't occur. If one ever appears, treat it as
     a plaintext secret (above).
   - **Secret found in history** (but not the tree) → it was removed but persists in past
     commits. Removing it now is **not** enough for a public repo — rewrite history with
     `git filter-repo --replace-text` (replace the literal with a redaction marker), then
     force-push, then realign other clones (`git fetch && git reset --hard origin/main`).
     Consider rotating the leaked credential regardless.

3. The history pass scans every commit, so on a large repo it can take a little time — tell
   the user it's working if it pauses.

## Notes

- Purely read-only; never modifies files or git state.
- Pattern-based, so it's a strong guard, not a proof of absence. Treat a clean result as
  "no high-signal leaks found," and still apply judgment for project-specific secrets.
- To add a new secret pattern, edit `EXTRA_PATTERNS` in `scripts/secret-scan.sh`.

## Script

```
scripts/secret-scan.sh
```
