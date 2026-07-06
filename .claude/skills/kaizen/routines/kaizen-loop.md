---
routine: kaizen-loop
description: Default 6-phase continuous-improvement cycle, expressed over ports.
profile: jarvis            # default binding; override with kaizen run --profile NAME
default_iters: 1
commit: local              # local commits, no push without consent · none = stage + message only
inner_per_outer: 3         # two-speed: K local inner green-spins per expensive outer review (eco)
stop: [reached_iters, backlog_dry, ci_red_twice, window_edge, user_intervened]
phases: [write, review, refactor, roadmap_okr, ci_merge, loop]
---

# Routine: kaizen-loop

The default cycle. This file is the SSOT for the **phase sequence only** — what "CI" / "roadmap" /
"passport" mean are **ports** (see [`../engine/ports.md`](../engine/ports.md)), bound by the profile.
Engine mechanics (L1–L6, window, eco, safety) live in [`../engine/loop-contract.md`](../engine/loop-contract.md);
here is just the per-phase intent. Each phase ends with a passport-report + checkpoint + tripwires.

## INIT (once per run)
- Read `profile.constitution` first (refuse to run if missing). Load recent passports from
  `profile.passport_store` + the resume-pointer. Open the `window.json` ledger.
- Show the 8-port readiness table (fail-fast). Verify branch policy via `safety_guard`.

## PLAN (start of each iteration)
- Pick the task by **leverage** (L1) from `profile.roadmap_source`: `(goal-advancement × unblock) ÷
  effort`. Right-size to the window remainder; don't start what you can't close.
- **Runtime telemetry as candidates:** before scoring, query `profile.passport_store` for
  `kind:friction` passports in the current window (tag-search; cheap read, no model). Each recurring
  friction is a task candidate ranked by the same leverage formula next to roadmap items — the
  backlog self-recharges from real pain instead of drying up (`backlog_dry`). Store empty or
  backend lacks search → roadmap-only, no failure.
- Passport: chosen task, score, time estimate, which goal/pillar; if telemetry-born — `ref` to the
  friction passport (the digest cites it).

## Phase 1 — write
**Goal:** one smallest valuable increment toward a product goal.
**Do:** take the PLAN task. **Reuse before writing** (grep the symbol; shared code → shared pkg).
Test-first for logic. **Two-speed (eco):** the inner write→test→green spin runs on `local_ai_hook`,
verified by `profile.ci_gate` (deterministic oracle), until green or no-progress.
**DoD:** code + tests written; compiles/imports. **Passport:** `kind=write`; task, files, new tests, goal.

## Phase 2 — review
**Goal:** catch real bugs before merge. **Do:** review depth by L3 — small/low-risk → single-pass
review skill; risky/large → adversarial `Workflow` (≥2/3 "real" before fixing). Review is **NO-LOCAL**
(remote model). Fix only real findings; out-of-scope → `spawn_task`.
**DoD:** real findings closed or consciously deferred. **Passport:** `kind=review`; raw→real, fixed, deferred.

## Phase 3 — refactor
**Goal:** quality without behavior change. **Do:** `/simplify`; remove dupes (consolidate into the
shared pkg). Tests from Phase 1 stay green. **DoD:** cleaner diff, nothing broken.
**Passport:** `kind=refactor`; what simplified, LOC ±.

## Phase 4 — roadmap_okr (backlog truth, D1)
**Goal:** doc ↔ code one again. **Do:** mark the task done in the **one** canonical track file
(`profile.roadmap_source` write-back); update phase status / KPI; document any new flag; file drift in
the drift sink. **DoD:** zero doc-code drift from this change. **Passport:** `kind=roadmap`; files/lines changed.

## Phase 5 — ci_merge (gate) + commit
**Goal:** merge-ready = green `profile.ci_gate`. **Do:** run scoped-to-diff (full before marking
merge-ready). 🔴 → fix this iteration; 🔴 again → **L4 revert** to last green + drift note → STOP. 🟢 →
local conventional commit (per `commit:`; **no push**); append run-event + `summary.json`.
**DoD:** repo 🟢 (with the feature, or reverted — but never broken). **Passport:** `kind=ci`; per-unit pass/fail, SHA.

## CRITIC + PASSPORT (end of each iteration)
- **L6 completeness critic:** doc-sync? new logic tested? flag documented? broken/out-of-scope leftovers?
  → `spawn_task`.
- **L2 passport:** write the iteration passport (summary + tags) to `profile.passport_store`.
- Update `window.json` (iter duration → burn-rate) and `resume.json` (L5).

## Phase 6 — loop
Check stop-conditions (incl. **window**: `remaining < avg_iter × 1.3` → wind-down + optional
`/schedule` next-window continuation). Else, iterations left → back to **PLAN** with the next task.
End → **FINISH**: self-score meta-OKR → render the daily digest. **Passport:** `kind=loop`; i/N, window left, decision.
