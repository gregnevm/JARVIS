# JARVIS `ci_gate` port — implementation SSOT

> The exact merge oracle for the JARVIS profile. Mirrors [`.github/workflows/ci.yml`](../../../../../.github/workflows/ci.yml).
> The engine calls this port; it never inlines these commands. Run **per-service** (the three `app`
> packages collide in one process).

## The matrix (exactly 6 services — `tts` is a known gap)

mypy is **strict via `pyproject.toml:9` (`strict = true`)**, not an inline `--strict` flag.
**Path asymmetry:** `jarvis_core` uses flat targets; the other 5 use `<svc>/app` + `<svc>/tests`.

```powershell
# scoped-to-diff: run only the services whose paths changed; full = all six before "merge-ready"
pytest jarvis_core/tests ; mypy jarvis_core
pytest gateway/tests     ; mypy gateway/app
pytest memory/tests      ; mypy memory/app
pytest tools/tests       ; mypy tools/app
pytest twin/tests        ; mypy twin/app
pytest hostagent/tests   ; mypy hostagent/app
# cheap_check (compose stays valid):
docker compose config --quiet
# task-success (опційний, ЛИШЕ коли live-стек піднятий; read-only сценарії):
# python training/eval/task_success.py --min-pass-pct 90
```

## Caveats (from the reuse audit — do not skip)
- **`tts` is a real service absent from the CI matrix** → flag it as an untested gap; do **not** claim
  "all services green". The first loop iteration may propose adding `tts` to the workflow.
- **NEVER replay `compose-validate`'s `cp .env.example .env`** (ci.yml:58) against the live working
  tree — it clobbers the real secret-bearing `.env`. `docker compose config` here runs against the
  existing `.env`; the `cp` step belongs only to a throwaway CI checkout.
- `hostagent` has **no** compose service (don't expect it in `docker compose config`).
- `status: red` on any touched service → engine triggers **L4 revert** (green-keeping invariant).
