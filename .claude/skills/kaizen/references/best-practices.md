# Kaizen — Best Practices (reuse · skills · artifacts · meta)

> Loaded on demand (progressive disclosure). The engine/loop run against ports; this is *how to work
> inside the phases* so each iteration reuses instead of reinventing. Generic — no repo specifics.
> Core rule: **don't write what you can reuse; don't do by hand what a skill does; don't leave an
> artifact without a passport.**

## 1. Reuse code (search before writing)
- Grep for the symbol and neighbors before creating a helper. Duplicated logic is debt the
  completeness critic and review will flag.
- Shared code goes to the product's **one** shared package — re-export, don't copy. Don't spawn a new
  shared package per need.
- Composition over a monolith: a new section = a new module with a `register()`-style hook + one wire
  line. A new transport/strategy = a new class, not an edit to an existing one (Open/Closed).
- **Reuse audit (security):** before depending on a found block, run the reuse-audit protocol
  (`engine/safety-contract.md` §6) — verify it exists at the cited line, check side-effects,
  tenant/ownership safety, secret-leak; record verdict + how_to_cite in the passport. Never depend on
  a `do-not-reuse` primitive.

## 2. Reuse skills (don't reimplement what exists)
Each phase should **call an existing skill** rather than hand-roll its job:

| Need | Skill | Instead of |
|------|-------|-----------|
| review a diff for bugs | `/code-review` | reading the diff by eye |
| thorough / risky review | adversarial multi-agent `Workflow` | one pass |
| remove dupes / simplify | `/simplify` | manual blind refactor |
| confirm a feature works | `/verify` | "seems to work" |
| security of changes | `/security-review` | trusting code-review |
| research an approach/API | `deep-research` | guessing from memory |
| out-of-scope finding | `spawn_task` | bloating the current diff |
| broad read-only search | an `Explore` agent | many manual reads |

**Review-depth rule (L3):** small/low-risk → single-pass review; risky/large → adversarial Workflow
(verify ≥2/3 "real" → fix only real). Workflow costs tokens — scale the pool to budget; explicit
opt-in for "ultra".

## 3. Artifacts & the context passport (P9/P10 analog)
Every significant artifact carries a passport: `kind` + `summary` + namespaced `tags` (+ embedding in
a rag-backend). An artifact without a passport is a bug.

Loop artifacts live under the profile's artifact dir:
```
passports/   # one passport per iteration (summary+tags) — L2, read first by the next iteration
window.json  # 5h-window ledger + burn-rate
resume.json  # resume-pointer (iter, task, phase, branch) — L5
runs/<id>/   # run.jsonl event stream + summary.json + rendered digest
reviews/     # saved review/Workflow reports (reused across iterations)
```
Tag passports so they serve **search** (`pillar:B AND status:done`) **and** addressing (pull a report
by tag). The next iteration reads them → no re-deriving, no repeating done work.

**Two surfaces, no duplication:** the run-log/digest is for the **human**; passports are machine
handles for the **loop**; statuses live in the **one** canonical track file. One fact, one place.

## 4. Meta-practices
- **Worktree isolation** for parallel/risky work, so concurrent edits don't conflict and the trunk
  tree stays clean.
- **`spawn_task`** for out-of-scope debt/vulns — don't widen the diff. High-confidence security
  findings especially.
- **`Workflow`** for fan-out (review lenses, multi-file audit, migration) — pipeline by default,
  barrier only when all results are needed together. Explicit opt-in (costs tokens).
- **Checkpoint commits** by phase-group, conventional messages, local + no push without consent;
  verify live VCS state first.
- **Doc-sync in the same commit:** close a task → mark done in the track file; add a flag → document
  it; find drift → file it in the drift sink.
- **Test-first for logic** (routing/parsers/guards/schemas) with mocked clients, no network/DB.

## 5. Anti-patterns
- ❌ Writing a helper that already exists (grep first).
- ❌ Reimplementing review/verify/simplify by hand.
- ❌ Leaving the repo red "to fix later" — L4-revert fires; don't accumulate debt in the tree.
- ❌ Writing an artifact (passport/report/ledger) without summary + tags.
- ❌ Starting a phase near the window edge you can't finish.
- ❌ Pushing to remote / merging without explicit consent.
- ❌ Duplicating facts across files (one fact, one place).
- ❌ An unbounded "return to 1" without N / stop-conditions.
