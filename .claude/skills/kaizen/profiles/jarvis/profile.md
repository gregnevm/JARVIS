---
profile: jarvis
accent_color: "#3aa657"
voice: "calm, factual, sentence-case, Ukrainian-friendly, emoji-free except the CI glyph"
score_weights:
  ci_green_rate: 0.30
  test_coverage_delta: 0.20
  backlog_burndown: 0.20
  token_efficiency: 0.15
  doc_sync: 0.15
artifact_dir: data/artifacts/self-improve   # path-alias (back-compat: keeps L2/L5 resume working)
synthetic_uid: -770001            # reserved negative id — never collides with a real (positive) Telegram id
loop_org: org_kaizen_loop         # dedicated org for redis_key(...) — NEVER pass None (unscoped legacy form)
ready: true
---

# Profile: jarvis (adapter / decorator)

> The **only** place "JARVIS" appears in the kaizen tree. Binds every port to a JARVIS concretion and
> owns the back-compat path-alias. Decorator, not a fork (DR5). All reuse below is **audit-verified**
> (`engine/safety-contract.md` §6) with mandatory wrappers — read the corrections, they are load-bearing.

## Port bindings

### 1. constitution
- **doc_path:** [`AGENTS.md`](../../../../../AGENTS.md) (mission S1–S5; principles P1–P10; C1 tag-everything;
  D1 doc-code-sync; §6 guardrails; §2 three pillars A/B/C — read first, never violate).
- **drift_sink:** [`docs/IMPROVEMENT_PROPOSALS.md`](../../../../../docs/IMPROVEMENT_PROPOSALS.md).

### 2. ci_gate → SSOT [`./ci-gate.md`](ci-gate.md)
Per-service `pytest + mypy` over `[jarvis_core, gateway, memory, tools, twin, hostagent]` +
`docker compose config --quiet`. mypy-strict from `pyproject.toml:9`. `tts` = known untested gap.

### 3. passport_store → **file-backend default (offline, working now)**, rag-backend = upgrade
- **default (zero services):** file-backend via
  [`kaizen/scripts/passport_store.py`](../../scripts/passport_store.py) →
  `data/artifacts/self-improve/passports/` (write / recency-read / AND-of-tags search). The loop runs
  fully **without** memory:8100 or Ollama. This is the active binding today.
- **upgrade (when `ENABLE_CONTEXT_API` + services up):** rag-backend via the gateway client-API —
  **write:** `POST /ingest/events`; **read:** `POST /context/search`
  ([`gateway/app/client_api/context.py`](../../../../../gateway/app/client_api/context.py); gated by
  `ENABLE_CONTEXT_API`; auth via `resolve_client_context`; derives `user_id/org_id` from
  `RequestContext`; applies `redactor.redact_passport` before store). The memory service itself has
  **no auth** and search is `user_id`-scoped only — never call `/context/*` directly or expose it.
- **tags:** `jarvis_core.passport.normalize_tags` ([`jarvis_core/passport/tags.py:31`](../../../../../jarvis_core/passport/tags.py)) —
  prepends a `kind:<kind>` tag (C1), pure. **Don't** duplicate `kind:` in the tag list (it injects it).
- **MANDATORY wrappers before `to_store`:** (a) **owner-injection** — set `user_id=-770001`,
  `org_id=org_kaizen_loop` from a dedicated synthetic `RequestContext` (replicating gateway
  `_build_store`); `to_store` carries **zero** tenant isolation by design. (b) **redaction** —
  `redactor.redact_passport` BEFORE store. Search is cosine `1-(embedding<=>vec)` + AND-of-tags
  (`tags @> $4`) + `since`, `user_id`-scoped. On store-unreachable the loop degrades to the
  file-backend default above (never blocks).

### 4. local_ai_hook → host Ollama (Vulkan) CHAT/EMBED — eco two-speed
- **inner loop candidate:** `AgentRunner.fix_tests` ([`tools/app/agent.py:986`](../../../../../tools/app/agent.py),
  via `POST /agent/code/fix`) — clean 4-status state machine `already_green|fixed|no_progress|stuck`.
  **Corrections (load-bearing):** (1) it is **NOT two-speed today** — single-model; the gate is a
  deterministic test re-run, not a second model. Cite it as *"would become the local inner loop"*. (2)
  "local" is qualified — the **model** is local Ollama but **test/edit execution crosses the network to
  the hostagent `/cli` endpoint** and mutates the real repo on disk. (3) headless `no_confirm=True`
  auto-applies edits → **requires** the blast-radius/path-scope wrapper (§7) before autonomous use.
- **embed:** local `nomic-embed-text` (768D) for passport-RAG → token-free at the model layer.
- **NO-LOCAL (stays on Claude):** outer adversarial review, security gate, L1 leverage, L6 completeness.

### 5. roadmap_source
- **read:** track checkboxes in `docs/{CODING_AGENT,API_PLATFORM,CLIENTS}_ROADMAP.md` (skip blocked:
  RunPod/GPU/cloud-secrets). Consider unblock-order from `docs/GAP_ANALYSIS.md`.
- **write-back (one canonical file):** `[x]` in the **track** roadmap (PRODUCT_ROADMAP = phase status
  only; AGENTS.md = no statuses). One fact, one place.

### 6. guardrails → `AGENTS.md` §6
No external-AI-as-default (S1); no `ENABLE_CODE_EXEC=true` without sandbox; no embed-model change
without migration; no SaaS feature that breaks self-hosted (S2); no artifact without a passport (C1);
no LangGraph/Celery/CrewAI/FastStream/n8n orchestrator (P6).

### 7. safety_guard
- branch-from-`main` (never commit to `main`); `commit: local` default (**no push** without consent);
  secrets only in `.env`. **kill-switch:** presence of `data/artifacts/self-improve/STOP` (or Redis
  `jarvis:{org}:kaizen:halt`) → immediate wind-down. **kill on CI-red-twice** (L4 then stop).
- **blast-radius (FAIL-CLOSED):** `allow_paths = [tools/**, jarvis_core/**, memory/**, gateway/**,
  hostagent/**, twin/**, docs/**, .claude/skills/**]`; `deny_paths = [.env*, .github/workflows/**,
  docker-compose.yml, **/migrations/**, mobile/**, db/**]`. **Enforced by real code:**
  [`jarvis_core/safety/blast_radius.py`](../../../../../jarvis_core/safety/blast_radius.py) —
  `BlastRadius.from_globs(allow, deny).partition(diff)` → `(allowed, blocked)`; pure, mypy-strict,
  fail-closed, deny-wins, basename-deny for secrets at any depth (24 tests
  [`test_blast_radius.py`](../../../../../jarvis_core/tests/test_blast_radius.py)). Blocked paths → human-gate.
- **synthetic-UID discipline:** every Redis key via `redis_key(org_id, *parts)`
  ([`jarvis_core/context.py:84`](../../../../../jarvis_core/context.py)) with `org_id=org_kaizen_loop` —
  **never `None`** (yields the unscoped legacy `jarvis:{parts}` form that can collide with prod keys).
  Org-prefix and ownership are **two separate controls** (adding an org prefix does not prevent IDOR).

### 8. guardrail_tripwires
- **DR1 engine-purity grep-gate:** `engine/**` + `kaizen/SKILL.md` must contain none of
  `jarvis|memory:8100|jarvis_core|AGENTS.md|docs/*ROADMAP|pytest <svc>` → match = build fail.
- secret-scan over the diff; import-smoke per touched service; `docker compose config --quiet`.
- **org-prefix tripwire** (raw `f"jarvis:..."` key without org-prefix, ref `redis_key`) +
  **ownership/IDOR tripwire** (ref `redis_store.get(owner_user_id=...)`) — separate signals.

## Verified reuse (audit-confirmed; verdict + how_to_cite)

| Primitive | Verdict | How to cite |
|---|---|---|
| `jarvis_core/passport` trio | safe-reuse + 2 wrappers | `to_store@models.py:49` (omits owner/org by design), `normalize_tags@tags.py:31` (prepends `kind:`), `format_context_block@retrieval.py:14`. **Wrap:** owner-injection + `redact_passport` before `to_store`. |
| `fix_loop.summary_signature` | safe-reuse (pure) | `@tools/app/tools/fix_loop.py:34` — 16-char sha1 over sorted-unique failed-test names. In-loop only; **not** the Redis/TTL tracker (`fail_signature:28`/`note_test_result:59` — keep Redis behind the adapter). |
| `AgentRunner.fix_tests` | reuse-with-care | `@tools/app/agent.py:986`. Cite as *"would become"* the local inner; exec crosses to hostagent `/cli`; headless auto-applies → needs blast-radius wrapper. |
| `MemoryClient.search_context` | reuse-with-care | `@tools/app/memory_client.py:37` POSTs `/context/search`. Route via gateway client-API (auth+redaction); mint a non-colliding synthetic `user_id`; **don't** pair with `_MemoryContextStore` (write side, no search). |
| memory `/context` routes + `db.search_context` | reuse-with-care | `routes.py:95/130`, `db.py:403`. Loop uses the **gateway** client-API, never memory `/context/*` directly (no auth, internal-only). |
| `JsonlLog` | safe-reuse as byte-sink | SSOT `jarvis_core/llm/jsonl_log.py` (`append`/`count`/`read_from`). `twin/app/session_log.py` is now a thin re-export of the SSOT (dedup done — `read_from` ported onto core). `computer_audit.py` is a **pattern to copy**, not import (JARVIS-domain). Engine's `run_jsonl.py` already adds per-run path + redaction + index. |
| `jarvis_core.context` (`redis_key`, `RequestContext`, `synthetic_context`, `DEFAULT_ORG_ID`) | reuse-with-care | `@jarvis_core/context.py:84/28/59/21`. `redis_key` = org-prefix control, **not** the IDOR gate. Pass explicit org, never `None`. (D1 drift: stale "consumed in PR#3" docstring to fix.) |
| `.github/workflows/ci.yml` | reuse-with-care | See [`ci-gate.md`](ci-gate.md). Derive pytest/mypy pairs declaratively; mypy-strict from `pyproject.toml:9`; `tts` gap; never replay `cp .env.example .env` on the live tree. |
