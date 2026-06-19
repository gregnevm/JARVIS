# Kaizen — Safety Contract (autonomy invariants)

> **SSOT for autonomy safety.** Generic invariants the engine enforces every iteration. The profile
> supplies concrete blast-radius globs + tripwire commands via the `safety_guard` and
> `guardrail_tripwires` ports. **A profile may only make safety STRICTER (DR7)** — never disable the
> kill-switch, green-keeping rollback, the fail-closed blast-radius, or widen eco LOCAL-OK zones.

## 1. Kill-switch (always checked at iteration start)
- The engine checks a profile-supplied stop signal (file/flag/key) **before every iteration**.
- Tripped → immediate **wind-down**: checkpoint → resume-pointer → one drift note → stop.
- A real-time quota/limit warning is treated the same as the kill-switch: wind-down, don't push through.

## 2. Blast-radius — FAIL-CLOSED
- The profile declares `allow_paths` (globs the loop may edit autonomously) and `deny_paths` (never,
  e.g. secrets/CI-config/infra/migrations).
- **Default deny when no allowlist is configured** — this inverts the common fail-open default. An
  edit outside `allow` or inside `deny` → hard human-gate, never a silent autonomous write.
- This is a **different axis** from `ci_gate`: the gate catches *broken*; blast-radius catches
  *unwanted-but-green* (a green commit into a file the user is actively editing, or into infra).

## 3. Green-keeping rollback (L4) — invariant
- The repo is **never** committed red. CI red after one fix attempt → revert this iteration's WIP to
  the last green checkpoint. CI red twice → kill-switch fires (stop + report). Reverted items are
  shown honestly (gray) in the digest, never hidden.

## 4. Commit / push policy
- Branch from the trunk; **never** commit to the trunk directly.
- Default `commit: local` → **no push without explicit consent**. Verify live VCS state before each
  commit (the human may commit between turns).
- Secrets live only in the secret store; nothing hardcoded, nothing surfaced in logs/diffs.

## 5. Human-gate calibration (ask rarely, but on substance)
- Don't confirm every action (kills autonomy) and don't never-confirm (kills safety). Use a
  **mutation budget per window**: X semi-reversible actions allowed without a human; on reaching X,
  one **batched** gate ("this window the loop made 8 committed refactors across 5 files — continue /
  show diffs / stop"), not per-step confirms. Hard/irreversible actions (push, delete, infra, secret
  files) **always** gate, regardless of budget.

## 6. Reuse-block audit (security of what the loop depends on)

Before depending on any reused code primitive, the loop runs the **DR1 reuse-audit protocol**:

1. **Verify it exists** at the cited `file:line` with the claimed signature (grep/read, not memory).
2. **Side-effects:** pure / network / DB / file / mutation? A "pure" claim that does I/O is a finding.
3. **Tenant/ownership:** if reused under a synthetic identity, is it IDOR-safe? Org-prefix and
   ownership are **two separate controls** — adding an org prefix does not prevent IDOR.
4. **Secret-leak:** could it read/emit a secret-bearing path?
5. **Verdict:** `safe-reuse` / `reuse-with-care (+ required wrapper)` / `do-not-reuse (+ reason)`.
   The engine must **never** import a `do-not-reuse` primitive. Every reuse is cited with its verdict
   and `how_to_cite` in the iteration passport (meta-OKR O4).

## 7. Between-phase tripwires (cheapest layer, run most often)
The profile supplies fast checks the engine runs between phases to abort early:
- **engine-purity grep-gate (DR1):** engine files matching repo-identifier strings = build fail.
- **secret-scan over the diff.**
- **import/compile smoke** per touched unit.
- **guardrail tripwires:** detect drift toward a prohibited dependency/orchestrator in the diff;
  org-prefix + ownership tripwires (two separate signals).

A tripwire that fires aborts the iteration before expensive review/commit and files a drift note.
