# Kaizen — Eco Policy (resource thrift WITHOUT quality loss)

> **SSOT for the eco-principle.** "Eco" means spending the **minimum compute that preserves quality** —
> not "use the cheap model everywhere." The tracked metric is **cost-per-felt-improvement**, not raw
> tokens. Profile-agnostic (DR1); the profile supplies the `local_ai_hook` endpoint.

## The objective-oracle deterministic-first ladder

Route each unit of work to the cheapest tier that doesn't hurt quality:

1. **Deterministic → free.** If a check can be a test/lint/compile/diff, run it — **zero model tokens**.
   This is `ci_gate`, signature dedup, the digest renderer, the status-line.
2. **Verified-fixable → local.** Mechanical work whose result is checked by a deterministic oracle
   (inner test-fix loop, embeddings, dedup, drafts) → `local_ai_hook`. The oracle (re-run the tests)
   catches a weak local model, so "local" is safe **because it's verified**, not assumed.
3. **Semantic / high-stakes → remote (capable model).** Final adversarial review, security gate,
   leverage (L1) and completeness (L6) judgment, architecture. These are the **NO-LOCAL zone**.

## Hard-fenced zones

| Zone | Tasks | Routing |
|------|-------|---------|
| **LOCAL-OK** | inner test-fix loop, embeddings (retrieval), fail-set dedup, rough drafts | `local_ai_hook`, verified by the deterministic oracle |
| **NO-LOCAL** | final review, security gate, L1 leverage, L6 completeness, architecture decisions | remote capable model only |

> **DR7 invariant:** a profile may **narrow** the LOCAL-OK zone (route *more* to remote), but may
> **never widen** it — it cannot send security/final-review to a local model. A NO-LOCAL-zone
> violation is an **automatic fail** (meta-OKR O3).

## Eco mechanisms (how the loop actually saves)

- **Two-speed loop.** Inner mechanical work local + verified by tests; outer expensive review runs
  **rarely** (every K green inner passes). Reserved for high-stakes diffs only.
- **No-progress early stop.** A pure fail-set signature ends a local fix loop the moment it stops
  making progress, instead of burning rounds.
- **Passport-RAG dogfood.** Semantic top-k retrieval over prior passports saves **input** tokens — the
  loop reads what's already known instead of re-deriving state. Embeddings are local → token-free at
  the model layer.
- **Deterministic form.** Sparkline, metric cards, deltas, status-line are computed in **pure code**
  (the renderer) — form quality is free and reproducible. The *only* prose the loop pays model tokens
  for is the before→after one-liners, and those just narrate already-measured numbers.
- **Live status costs zero.** The status-line is recomputed locally from run-state each tick, never
  re-queried from the model.
- **Budget-aware fan-out.** The adversarial pool scales to the window remainder.
- **Progressive disclosure** (token-thrift on the skill itself): `SKILL.md` stays short; engine refs
  are loaded only when the relevant phase runs.
- **Eco on the loop's own instrumentation.** The run-event sink uses an in-memory line counter (no
  O(n) recount per append).

## The one genuinely ambiguous boundary

"Review of a *trivial* diff" is the borderline case. Default: a diff under the profile's
small-diff threshold and touching no NO-LOCAL path may use the single-pass remote review (still
remote — review is NO-LOCAL); only the *depth* (single vs adversarial) drops, never the model tier.
A profile may pin a stricter threshold but cannot move review to local.
