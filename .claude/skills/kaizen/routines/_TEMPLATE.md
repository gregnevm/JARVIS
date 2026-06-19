---
routine: <kebab-name>
description: <one line — what this cycle improves and why>
profile: <profile-name>    # which adapter binds the ports
default_iters: 1
commit: local              # local commits no push · none = stage + message only
inner_per_outer: 3         # two-speed: local inner spins per remote outer review (eco); omit if N/A
stop: [reached_iters, backlog_dry, ci_red_twice, window_edge, user_intervened]
phases: [<phase1>, <phase2>, ...]
---

# Routine: <kebab-name>

<1–2 lines: what this routine does, which product goal it advances, when to run it.>
A routine is the SSOT for the **phase sequence only**. Everything repo-specific is a **port**
([`../engine/ports.md`](../engine/ports.md)), bound by the profile. Engine mechanics (L1–L6, window,
eco, safety) live in [`../engine/loop-contract.md`](../engine/loop-contract.md) — don't restate them.

## INIT (once per run)
- Read `profile.constitution`; load recent passports + resume-pointer; open `window.json`; show the
  8-port table (fail-fast); check branch policy via `safety_guard`.

## PLAN (each iteration)
- Pick the task by leverage (L1) from `profile.roadmap_source`; right-size to the window remainder.

## Phase 1 — <name>
**Goal:** … **Do:** … (which skills/Workflow/ports) **DoD:** … **Passport:** `kind=<name>`; …

## Phase 2 — <name>
**Goal:** … **Do:** … **DoD:** … **Passport:** `kind=<name>`; …

<!-- add phases as needed; reference ports, never repo nouns -->

## CRITIC + PASSPORT (end of each iteration)
- L6 completeness critic → `spawn_task` for leftovers; L2 passport → `profile.passport_store`;
  update `window.json` + `resume.json`.

## Last phase — loop
Check stop-conditions (incl. window wind-down). Iterations left → back to PLAN. End → FINISH:
self-score meta-OKR → render the daily digest.
