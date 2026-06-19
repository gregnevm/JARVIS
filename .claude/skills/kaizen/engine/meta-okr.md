# Kaizen — Meta-OKR (the loop's own goals, inherited by every profile)

> **The product's North Star, embedded as a measurable contract.** This is both shipped guidance
> **and** self-scored each run: the engine scores itself against these KRs at FINISH, writes the score
> to `passport_store`, and re-reads it at INIT — so the loop improves **itself**, not just the repo.
> A profile may **ADD** KRs; it may **never drop** the four core objectives (DR7-adjacent invariant).

## North Star
> **Every day the product is measurably and visibly better** — a portable self-improvement coroutine
> that ships **≥1 felt improvement per run**, **never leaves the repo broken**, and spends the
> **minimum compute that preserves quality**.

## O1 — Improvements are FELT (not asserted)
- Each run produces **≥1 user-visible / dogfood-observable delta** with a concrete `before → after`
  one-liner. A run with no measurable before/after renders a **yellow** meta-KR dot and biases the
  next PLAN toward user-visible leverage.
- **felt-delta rate** (% of runs the user can name a before/after) trends up over the 7-day window;
  the 7-day kaizen-score sparkline is non-decreasing.
- Every shipped item carries a passport (P9/P10/C1 analog). **Artifact without passport = 0 felt credit.**

## O2 — Green-keeping (repo never left red)
- The repo is **never committed red**: CI-red after one fix attempt triggers L4 revert-to-last-green
  (the DR7 invariant).
- **green-streak** count tracked across runs; a broken streak is a meta-regression flagged in the digest.
- Reverted items shown honestly (gray), never hidden — felt safety builds the trust that keeps the
  loop running daily.

## O3 — Eco without quality loss (local-first where it doesn't hurt)
- The **inner-local vs outer-remote** call ratio is reported per run; structural/layout work spends
  **zero** model tokens (deterministic renderer + local status-line).
- **Zero quality regressions from eco routing:** a remote-review or security-gate skipped on a
  high-risk diff (NO-LOCAL-zone violation) is an **automatic fail**.
- Budget adherence within the 5h-window ledger; **cost-per-felt-improvement** is the tracked
  efficiency metric, not raw token count.

## O4 — Backlog truth & safety (trust the displayed progress)
- **Zero doc-code drift** introduced (measured by the completeness critic); `roadmap_source`
  write-back accuracy = 100% (closed task → done-mark in the one canonical track file, same commit).
- Every autonomous iteration passes `safety_guard` (within blast-radius, branch-from-trunk, no
  unconsented push) and the between-phase tripwires; the kill-switch demonstrably fires on CI-red-twice.
- **Reuse-block audit:** any reused primitive is cited with verdict + `how_to_cite`; `do-not-reuse`
  primitives are never imported by the engine.

---

## How it self-scores
At FINISH the engine computes a per-objective score from **measured run-facts** (not opinion):
O1 from felt-delta presence, O2 from the green-streak + revert count, O3 from the local/remote ratio +
any NO-LOCAL violation, O4 from drift count + safety/tripwire passes + reuse-audit completeness. The
composite is the **kaizen-score** (0–100) shown in the digest. The score and its deltas drive the
sparkline (O1) and bias next-run PLAN — the loop is accountable to its own promise on its own surface.

> Routines and profiles should reference these objectives as the *why* behind each phase, so the
> model acts on intent, not rote steps.
