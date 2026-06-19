---
profile: <product-name>
accent_color: "#3aa657"     # one accent per profile (visual identity); green = growth default
voice: "calm, factual, sentence-case, emoji-free except the CI glyph"
score_weights:              # kaizen-score composite (engine supplies arithmetic; you set weights)
  ci_green_rate: 0.30
  test_coverage_delta: 0.20
  backlog_burndown: 0.20
  token_efficiency: 0.15
  doc_sync: 0.15
ready: false                # flip to true only when all 8 ports below are filled
---

# Profile: <product-name> (adapter)

> A profile is a **decorator**: it ADDS bindings around the generic engine, never copies loop logic
> (DR5). Fill **all 8 ports** or the engine refuses to run (DR3). A profile may make safety/eco
> **stricter**, never weaker (DR7). Copy this folder, run `kaizen init`, and the wizard walks each port.

## Port bindings (the 8-port checklist)

### 1. constitution
- **doc_path:** `<path to the read-first charter>`
- **principle_refs:** `<anchors>` · **guardrail_ref:** `<...>` · **drift_sink:** `<path>`

### 2. ci_gate
- **command (scoped + full):** `<the green-or-red oracle; put the SSOT in ./ci-gate.md if large>`
- **cheap_check:** `<fast pre-check>`

### 3. passport_store
- **backend:** `file` (default, `data/artifacts/<profile>/passports/`) **or** `rag` (semantic).
- **rag endpoint / client:** `<auth'd ingest + search; never a bare unauth'd vector endpoint>`
- **tag normalizer:** `<the product's tag SSOT, or the engine default>`
- **required wrappers:** owner-injection + redaction BEFORE store (if the store has no tenant isolation).

### 4. local_ai_hook
- **endpoint:** `<local model for inner fix/embed/dedup/draft, or "none" → remote fallback>`
- **LOCAL-OK narrowing:** `<any tasks you keep remote beyond the engine default>` (cannot widen).

### 5. roadmap_source
- **read (actionable tasks + leverage signals):** `<where>` · **write-back (one canonical file):** `<where>`

### 6. guardrails
- **prohibitions:** `<the "consciously NOT doing" list>`

### 7. safety_guard
- **branch/commit/push:** `<policy>` · **allow_paths:** `<globs>` · **deny_paths:** `<secrets/infra/...>`
- **kill-switch signal:** `<file/flag/key>` · **human-gate budget:** `<X mutations/window>`

### 8. guardrail_tripwires
- **between-phase checks:** `<grep-gate, secret-scan, import-smoke, ...>`

## Verified reuse (audit before depending — engine/safety-contract.md §6)
| Primitive | Verdict | How to cite (file:line + required wrapper) |
|---|---|---|
| `<block>` | safe-reuse / reuse-with-care / do-not-reuse | `<...>` |
