# Kaizen — Loop Contract (the generic engine)

> **SSOT for the loop itself.** The algorithm + L1–L6 + 5h-window logic, written against **ports
> only** (see `ports.md`). The concrete per-repo *phase sequence* lives in a routine, not here. This
> file contains **zero** repo-specific strings (DR1).

A **run** = N iterations. An **iteration** = the routine's phases in order. Default `N=1` — never
loop unbounded.

```
INIT   → read profile.constitution (refuse if missing); load recent passports (profile.passport_store)
         + resume-pointer; open the 5h-window ledger; show the 8-port status table (fail-fast).
LOOP i = 1..N:
  PLAN     → pick task by leverage (L1) from profile.roadmap_source; right-size to window remainder.
  PHASES   → run routine phases; after each: passport-report → checkpoint-commit (L5) → tripwires (port 8).
  CI-GATE  → profile.ci_gate(changed_paths): green → commit + digest; red → fix in-iteration;
             red again → L4 revert to last green checkpoint + drift note; safety_guard.kill check.
  CRITIC   → completeness critic (L6): doc-sync, test coverage, flag docs, out-of-scope → spawn task.
  PASSPORT → write iteration passport (summary+tags) to profile.passport_store.
  STOP?    → evaluate stop-conditions; if met, update resume-pointer and break.
FINISH → self-score meta-OKR (meta-okr.md) → write to passport_store → render daily digest.
```

## L1–L6 (the improvements, port-expressed)

- **L1 — leverage task selection.** Not "next unchecked"; pick max
  `(goal-advancement × unblock-factor) ÷ effort` from `roadmap_source`. Unblockers/foundation rank
  higher. Record the score in the PLAN passport. *Why: the loop must not drift onto cheap low-value work.*
- **L2 — context passport between iterations.** Every iteration leaves a passport (summary + namespaced
  tags) in `passport_store`. Next iteration reads them first → no re-deriving repo state, no repeating
  done work. *This is the loop eating its own dogfood (the artifact contract applied to itself).*
- **L3 — adaptive review depth.** Small/low-risk diff → single-pass review skill. Large diff, or one
  touching auth/secrets/mutations/money → adversarial multi-agent review (verify ≥2/3 "real" before
  fixing). The threshold is explicit so cheap diffs don't burn budget and risky ones aren't under-reviewed.
- **L4 — green-keeping rollback.** The repo is **never** left red. CI red after one fix attempt →
  revert this iteration's WIP to the last green checkpoint and file the problem in the drift sink.
  A clean repo without the feature beats a dirty one with it.
- **L5 — checkpoint + resume-pointer.** Commit by phase-group (not only at the end); keep a
  `resume.json` (iteration, picked task, phase, branch). A hard stop loses nothing — the next run
  continues from the pointer.
- **L6 — completeness critic.** End-of-iteration single pass: doc-sync done? new logic tested? flag
  documented? anything left broken/out-of-scope? Findings → spawned task, not into the current diff.

## Stop-conditions (check at end of each iteration)

Stop and report if **any** hold:
- reached `N` iterations (default 1 — don't loop without an explicit ask);
- `backlog_dry` — `roadmap_source` has no actionable non-blocked task;
- `ci_gate` red twice in a row despite a fix (after L4 revert);
- **window/budget at the edge** — remainder won't fit another full iteration (see below);
- user intervened.

> "Repeat" means *next iteration within N*, never an unbounded loop. On a window stop, update the
> resume-pointer and (with consent) schedule continuation next window.

## 5h-window / budget ledger

Honest: the exact rolling-quota remainder is **not** programmatically readable from inside a run. Plan
by **wall-clock + a burn ledger**, and build the loop so hitting the limit never costs lost work.

`window.json` (in the profile's artifact dir): `{ window_start (real clock), window_hours, iterations:[{i,start,end,phases_ok,note}], avg_iter_minutes }`.

1. **Right-size to remainder:** `remaining ≈ window_hours·60 − (now − window_start)`. Pick a task
   (L1) that fits with room for `ci_gate`. Don't start a phase you can't close.
2. **Front-load cheap+valuable;** keep expensive adversarial review for when budget is ample.
3. **Wind-down threshold:** when `remaining < avg_iter_minutes × 1.3`, do **not** start a new
   iteration — bring the current one to green+committed, update the resume-pointer, report.
4. **Chain windows:** at wind-down, with consent, schedule continuation at ≈ `window_start + window_hours`.
5. **Budget-aware fan-out:** if a token target is set, scale the adversarial pool to the remainder.

The tracked efficiency metric is **cost-per-felt-improvement**, not raw tokens (see `meta-okr.md` O3).
