---
name: kaizen
description: >-
  Portable continuous self-improvement engine for any code repository — the "vibe coding" coroutine:
  run it and the product gets measurably, visibly better every day. Runs a bounded multi-phase loop
  (plan → write → review → refactor → roadmap/OKR → CI-gate → repeat) that picks the highest-leverage
  task, keeps the repo green (never committed broken), reuses code/skills/artifacts, audits what it
  reuses, spends the minimum compute that preserves quality (local-first two-speed), and ships a felt
  daily digest. The repo it works on is a pluggable PROFILE (adapter); the engine is generic. Use when
  the user says: "self-improve the repo", "run the kaizen loop", "continuous improvement coroutine",
  "make the product better every day", "set up auto-improvement for this repo", "run/define a
  self-improvement routine", or invokes a specific repo profile. For repeatable autonomous
  improvement cycles — not one-off edits.
---

# kaizen — continuous self-improvement engine

A portable engine that runs a bounded self-improvement **loop** over any repo. The repo-specific
parts live in a **profile** (a decorator/adapter); the engine speaks **ports**, never repo nouns —
so the same engine improves any product. Launch the coroutine, get a better product daily.

> **Architecture (Ports & Adapters / Hexagonal).** Read [`engine/ports.md`](engine/ports.md) for the
> 8-port contract a profile fills. The engine is in `engine/`; adapters are in `profiles/`. This file
> is the **entrypoint + router** and contains **zero** repo-specific strings (invariant DR1).

## Commands (full form in [`references/cli-contract.md`](references/cli-contract.md))

| Command | Does |
|---|---|
| `kaizen run [--iters N=1] [--profile auto]` | run the default routine 1 iteration; local commit; **no push**; auto-detect profile |
| `kaizen status [--full]` | the one live status-line |
| `kaizen init [--profile NAME]` | scaffold a profile from the repo (zero questions if confident) |
| `kaizen profile [show\|list\|edit]` | the active profile's 8-port readiness table |
| `kaizen report [<run-id>=today] [--full]` | render the daily digest |

Bare `kaizen` → `status` if a run exists, else a one-line hint. Unknown verb → show this table.

## Running a routine (the loop)

1. **Resolve the profile** (`--profile`, else auto-detect, else the active one). The profile must fill
   **all 8 ports** or the engine **refuses to run** (fail-fast, DR3). Show the port-status table first.
2. **Execute the loop** per [`engine/loop-contract.md`](engine/loop-contract.md): `INIT → (PLAN →
   phases → CI-gate → CRITIC → PASSPORT)×N → FINISH`, with improvements **L1–L6** and the 5h-window
   ledger. Run **strictly sequentially, no permission prompts between phases**; a short passport-report
   after each phase.
3. **Eco routing** per [`engine/eco-policy.md`](engine/eco-policy.md): cheap/inner work →
   `local_ai_hook`; final review + security + leverage/completeness judgment stay remote (NO-LOCAL
   zone). A profile may narrow LOCAL-OK, never widen (DR7).
4. **Safety every iteration** per [`engine/safety-contract.md`](engine/safety-contract.md): kill-switch,
   **fail-closed** blast-radius, green-keeping rollback, batched human-gate, reuse-audit. A profile may
   only make this stricter.
5. **CI-gate** (`profile.ci_gate`) is the merge oracle; red → L4 revert; the engine never inlines the
   command.
6. **FINISH:** self-score the [`engine/meta-okr.md`](engine/meta-okr.md), write it to `passport_store`,
   and render the daily digest (`scripts/render_digest.py` from `summary.json`).

> **Meta-OKR is inherited by every profile** — the loop is accountable to its own promise (ship a felt
> improvement daily, keep the repo green, stay eco without quality loss, keep the backlog truthful).
> See [`engine/meta-okr.md`](engine/meta-okr.md).

## Creating / running routines

- **Routines** (`routines/`) define the *phase sequence* only; everything else is a port. The default
  is [`routines/kaizen-loop.md`](routines/kaizen-loop.md). New routine = copy `routines/_TEMPLATE.md`.
- **Profiles** (`profiles/`) are the adapters. New repo = copy `profiles/_TEMPLATE/` and fill the 8
  ports (`kaizen init` walks them). Each repo's binding lives under its own `profiles/<name>/`.

## How work is done inside phases
See [`references/best-practices.md`](references/best-practices.md): reuse code (grep before writing),
reuse skills (`/code-review`, `/simplify`, `/verify`, `/security-review`, `deep-research`,
`spawn_task`, `Workflow`), artifacts + passports, and the meta-practices. **Audit every reused block**
before depending on it (`engine/safety-contract.md` §6).

## Form (it must be *felt*)
The renderer ([`scripts/render_digest.py`](scripts/render_digest.py)) and event sink
([`scripts/run_jsonl.py`](scripts/run_jsonl.py)) are **pure, deterministic, zero-token** — form quality
is free. The daily digest ([`references/digest-format.md`](references/digest-format.md)) makes every
improvement felt via a mandatory `before → after` per item and a 7-day score sparkline. Reverted items
are shown honestly (gray), never hidden — felt safety is what keeps the loop running daily.
