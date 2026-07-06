# Kaizen — Daily Digest Format (the felt-delta artifact)

> **FORM SSOT.** One digest per run, rendered **deterministically** by `scripts/render_digest.py`
> from `summary.json` — **zero LLM tokens on layout**. Fixed 5-block order so the eye learns it once.
> Graceful degradation: HTML card → markdown+ASCII → 3-line push, with the **score / before-after /
> risk** triad preserved at every size. Both renderers (md/html) consume this one schema → channel
> parity, guarded by a snapshot test.

## `summary.json` — the stable input schema (the only contract the renderer reads)

```json
{
  "run_id": "2026-06-18-1",
  "day": 7,
  "iters": 4,
  "duration_min": 73,
  "ci": "green",                         // green | red | mixed
  "kaizen_score": 78,                    // 0..100 composite
  "score_delta": 6,                      // vs previous run
  "score_history": [60,63,63,68,71,72,78],  // last 7 runs (for sparkline)
  "shipped": [
    {"title": "passport-RAG retrieval in PLAN",
     "before": "re-derived repo state every iter",
     "after": "1 /context call, top-5 prior iters",
     "pillar": "B", "passport": true,
     "friction_ref": ""}   // optional (SY-1): ref of the kind:friction passport that spawned
  ],                       // the task; BLOCK 4 renders "· from telemetry: `ref`"
  "tests_delta": "+18",
  "tokens": {"total": 412000, "inner_local": 280000, "outer_remote": 132000, "delta_pct": -32},
  "reverted": [{"title": "repo_grep AST refactor", "reason": "mypy red twice"}],
  "risks": [{"title": "rate-limit double-count", "task": "spawned:abc12"}],
  "meta_kr": {"felt": true, "green_streak": 5, "eco_no_local_violation": false, "drift": 0}
}
```

`kaizen_score` = profile-weighted composite of: CI-green-rate, test-coverage delta, backlog-burndown,
token-efficiency (cost-per-felt-improvement), doc-sync. **Engine renders identically; the profile
sets the weights.** A run that ships **no measurable before/after** → `meta_kr.felt=false` → yellow dot.

## The fixed 5-block order

**BLOCK 0 — META-OKR HEADER STRIP**
`Objective: ship a felt improvement daily · KR: kaizen-score trend up over 7d`
*(the skill measures its own promise on its own surface.)*

**BLOCK 1 — HEADER**
`day N · run-id · iters · duration · [CI badge]` — the one colored traffic-light glyph.

**BLOCK 2 — 4 METRIC CARDS**
(a) **kaizen-score** 0–100 big + signed delta · (b) **shipped** count · (c) **tests ±** ·
(d) **tokens ±** with inner-local / outer-remote split.

**BLOCK 3 — 7-DAY SPARKLINE**
ASCII (`▂▃▃▅▆▆█`) or SVG of `score_history` — the single most felt artifact: slow compounding made a
visible upward line. Footer **meta-KR dot-row**: green = felt delta shipped, yellow = no measurable
before/after, gray = reverted.

**BLOCK 4 — WHAT CHANGED TODAY**
Each shipped item with a **mandatory** `before → after` one-liner drawn from **measured run-facts**
(`before: 60k tokens/iter · after: 41k (-32%)`). If the loop cannot produce a measured before/after,
the item renders **muted** and the meta-KR dot goes **yellow** — *this is THE mechanism that makes
improvement felt, not asserted.*

**BLOCK 5 — RISK / REVERTED + ACTIONS**
Reverted items in **gray** (honest, not hidden); each risk links a spawned task; 3 action buttons
(`sendPrompt`): **See full report · Run again · Explain revert** — turning a passive report into a
one-click loop.

## Degradation ladder (same content, three sizes)
- **HTML card** (web/inline) — full 5 blocks, SVG sparkline, action buttons.
- **markdown + ASCII** (terminal/chat) — same 5 blocks, ASCII sparkline, link actions.
- **3-line push** — `day N · score X (+Δ) · shipped: <top item before→after>`.

The block order and the score/before-after/risk triad **survive every channel**. The markdown
rendering is covered by a CI snapshot test so the two channels never drift.
