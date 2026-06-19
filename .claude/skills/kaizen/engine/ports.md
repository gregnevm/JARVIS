# Kaizen — Port Interface (the hexagon boundary)

> **SSOT for the contract between the generic engine and any product.** This file is the *only*
> thing the engine reads to know what a profile guarantees. The engine is profile-agnostic — it
> speaks **ports**, never repo nouns. A profile (decorator/adapter) binds every port to a concretion.
>
> **A profile MUST fill ALL 8 ports or the engine refuses to run** (fail-fast, DR3). Partial profiles
> are an error, not a silent default.

Each port below: **contract** (what the engine expects), **IN/OUT** shape, **failure mode**, and
**eco-tier** (does the engine treat this as cheap/local-OK or expensive/remote — see `eco-policy.md`).

---

## 1. `constitution` — read-first charter
- **Contract:** path(s) to the product's living charter the loop MUST read first and never violate,
  plus principle/guardrail anchors and a drift sink.
- **IN:** none. **OUT:** `{ doc_path, principle_refs[], guardrail_ref, drift_sink_path }`.
- **Failure:** doc missing → engine refuses to start (no constitution = no autonomous run).
- **Eco-tier:** read-once per run, cached in context (progressive disclosure).

## 2. `ci_gate` — green-or-red merge gate
- **Contract:** the objective oracle. MUST be runnable **scoped-to-diff** and **full**. Engine treats
  `red` as the L4-rollback trigger; it **never inlines** the command.
- **IN:** `{ changed_paths[] }`. **OUT:** `{ status: green|red, per_unit:[{unit,pass}], cheap_check }`.
- **Failure:** gate cannot run → treat as red (fail-closed).
- **Eco-tier:** deterministic, **zero model tokens** — this is the free verification layer.

## 3. `passport_store` — felt-history memory (L2)
- **Contract:** where iteration context-passports are written/queried. MUST degrade offline
  (store-without-vector). Two impls allowed: **file-backend** (default,
  `data/artifacts/<profile>/passports/`) and **rag-backend** (semantic retrieval).
- **IN(write):** `{ kind, summary, tags[], ref }`. **IN(read):** `{ query|tags[], top_k }`.
  **OUT:** passport handles / RAG hits.
- **Failure:** store unreachable → fall back to file-backend mirror; never block the loop.
- **Eco-tier:** retrieval saves **input** tokens (read what's known vs re-derive); embeddings local.

## 4. `local_ai_hook` — optional local model for eco two-speed
- **Contract:** a local model endpoint. Engine routes **cheap/inner-loop** work here (see
  `eco-policy.md` for the hard-fenced LOCAL-OK list); reserves **remote/outer** review for
  high-stakes. **Absent hook → engine falls back to remote for everything** (graceful, never breaks).
- **IN:** `{ task: fix_tests|embed|dedup|draft, prompt }`. **OUT:** `completion | vector`.
- **Failure:** local endpoint down → transparent remote fallback for that task only.
- **Eco-tier:** this port *is* the eco lever. A profile may **narrow** LOCAL-OK zones, never widen (DR7).

## 5. `roadmap_source` — backlog-truth layer (D1)
- **Contract:** where actionable tasks live + where status is written back. Drives L1 leverage
  selection and the `backlog_dry` stop-condition. Never hardcodes file names.
- **IN(read):** actionable non-blocked tasks with leverage signals (pillar/goal, unblock-factor).
  **IN(write):** mark done in the **one canonical** track file. **OUT:** task list + write confirm.
- **Failure:** no actionable tasks → `backlog_dry` stop (honest), not an error.
- **Eco-tier:** read cheap; selection (L1) is reasoning — keep on the capable model.

## 6. `guardrails` — the "consciously NOT doing" list
- **Contract:** hard prohibitions the loop must never cross. Engine checks **before committing**.
- **IN:** `{ proposed_change }`. **OUT:** `{ allowed: bool, violated_rule? }`.
- **Failure:** ambiguous → treat as violated (fail-closed), surface to human.
- **Eco-tier:** cheap rule-check; deterministic where possible.

## 7. `safety_guard` — autonomy envelope
- **Contract:** kill-switch, blast-radius caps, branch/commit/push policy. Consulted **every
  iteration**. Blast-radius default is **FAIL-CLOSED** (deny when no allowlist configured).
  A profile may only make this **stricter** (DR7), never weaker.
- **IN:** `{ iteration_diff }`.
  **OUT:** `{ within_blast_radius: bool, may_commit: bool, may_push: bool, kill: bool }`.
- **Failure:** guard cannot decide → `kill: true`.
- **Eco-tier:** cheap, runs always.

## 8. `guardrail_tripwires` — cheap continuous checks between phases
- **Contract:** fast eco-cheap signals that abort an iteration **before** expensive work (not just at
  `ci_gate`). Run between phases.
- **IN:** none. **OUT:** `{ tripped: bool, signal }`.
- **Failure:** a tripwire itself erroring → treat as tripped (fail-closed), report.
- **Eco-tier:** the cheapest layer — runs most often, must cost near-zero.

---

## Port summary (the table the engine shows on `kaizen run`)

| # | Port | Direction | Engine refuses to run without it | Eco-tier |
|---|------|-----------|----------------------------------|----------|
| 1 | constitution | driven | ✅ | read-once |
| 2 | ci_gate | driven | ✅ | deterministic / free |
| 3 | passport_store | driven | ✅ (file-backend min) | retrieval-cheap |
| 4 | local_ai_hook | driven | ❌ (graceful remote fallback) | **the eco lever** |
| 5 | roadmap_source | driven | ✅ | read-cheap |
| 6 | guardrails | driven | ✅ | rule-cheap |
| 7 | safety_guard | driven | ✅ | always-on cheap |
| 8 | guardrail_tripwires | driven | ✅ | cheapest |

> **Dependency rule (DR2):** profiles and routines may reference `ports.md` and `loop-contract.md`;
> the engine may **never** reference a profile or routine by name. Adapters depend inward.
