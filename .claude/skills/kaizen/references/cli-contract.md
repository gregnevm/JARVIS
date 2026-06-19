# Kaizen — CLI Contract (the 5-verb surface)

> **FORM SSOT for the commands.** Five predictable verbs, smart defaults, no command needs args to do
> the right thing, and every default is the safe/cheap one. Progressive disclosure: terse by default,
> `--full` to expand.

## Commands

| Command | Default behavior | Flags |
|---------|------------------|-------|
| `kaizen run` | run the default routine **1 iteration**, local commit, **no push**, auto-detect profile | `--iters N` (default 1) · `--profile NAME` (default auto) · `--routine NAME` · `--dry` |
| `kaizen status` | print the one live status-line for the current/last run | `--full` (per-iter detail) |
| `kaizen init` | scaffold a profile from the repo (detect stack); **zero questions if confident** | `--profile NAME` · `--force` |
| `kaizen profile` | `show` the active profile's 8-port table; `list`; `edit` | `show`(default)·`list`·`edit` |
| `kaizen report` | render the daily digest for **today**'s run | `<run-id>` · `--full` · `--md`/`--html` |

**Rule:** unknown/typo'd verb → show this table. Bare `kaizen` → `kaizen status` if a run exists, else
a one-line "run `kaizen run` to start; `kaizen init` to set up a new repo."

## Port-status table (shown on `kaizen run` and `kaizen profile show`)

Fail-fast made visible — 8 ports as rows so "is this profile ready" is instant:

```
profile: jarvis                                    ● ready (8/8 ports)
  port               bound  backend                         last
  constitution        ✓     AGENTS.md                       ok
  ci_gate             ✓     per-service pytest+mypy          green
  passport_store      ✓     client-API /context (rag)        ok
  local_ai_hook       ✓     host Ollama (two-speed)          ok
  roadmap_source      ✓     docs/*ROADMAP track files        ok
  guardrails          ✓     AGENTS.md §6                     ok
  safety_guard        ✓     blast-radius + no-push           armed
  guardrail_tripwires ✓     grep-gate + secret-scan          ok
```

A missing port renders `✗` and the engine **refuses to run** (DR3).

## Status-line grammar (one glanceable, channel-agnostic line)

Fixed left-to-right order; the **CI-light is the only colored glyph**, everything else neutral:

```
who > day > progress > current-task+phase > CI-light > budget > window
kaizen > day7 > iter 2/4 > CA-4.1 review > ● green > 41k tok > 18m left
```

The same line drives CLI, chat, and web. Recomputed locally from run-state each tick (zero tokens).

## Progressive disclosure (three depths)
1. **status-line** — always available (`kaizen status`).
2. **digest card** — default after a run (`kaizen report`).
3. **full report** — opt-in (`report --full`): per-iter passports, raw findings, ledger.

## Visual identity
Name **kaizen** + a seedling mark + **one accent color per profile** (green = growth, default),
sentence-case, calm flat surfaces, **emoji-free except the single CI traffic-light glyph**. So the
user always trusts "this is my improvement loop talking" across CLI / web / chat.
