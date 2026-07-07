"""`jarvis doctor` — one-command діагностика self-hosted стека (packaging DX).

Паттерн поля (`docs/COMPETITIVE_ANALYSIS.md` §3.9: QwenPaw/OpenJarvis `doctor`):
один запуск каже, що зі стеком не так — health сервісів, доступність пісочниці,
наявність критичних env, досяжність Ollama. Реюз наявних `/health` контрактів;
чистий збір (ін'єкція client/локальних чеків) → тестовно без мережі.

  python -m app.doctor                 # людський вивід + exit 0/1
  python -m app.doctor --json          # машинний
Exit 1, якщо будь-який критичний чек (critical=True) провалився.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Callable

import httpx

from .config import settings

# Сервіс → (env-база URL, критичність). tools — self, беремо локально.
_SERVICES: tuple[tuple[str, str, bool], ...] = (
    ("memory", "http://memory:8100", True),
    ("twin", "http://twin:8765", False),
    ("tts", "http://tts:8300", False),
    ("whisper", "http://whisper:8400", False),
)


def check_service(name: str, url: str, *, critical: bool, client: httpx.Client) -> dict[str, object]:
    try:
        resp = client.get(f"{url.rstrip('/')}/health", timeout=5.0)
        ok = resp.status_code == 200
        return {"name": f"service:{name}", "ok": ok, "critical": critical,
                "detail": f"HTTP {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"name": f"service:{name}", "ok": False, "critical": critical,
                "detail": f"недосяжний: {type(exc).__name__}"}


def check_ollama(client: httpx.Client) -> dict[str, object]:
    url = settings.ollama_host.rstrip("/")
    try:
        resp = client.get(f"{url}/api/tags", timeout=5.0)
        return {"name": "ollama", "ok": resp.status_code == 200, "critical": True,
                "detail": f"HTTP {resp.status_code} @ {url}"}
    except httpx.HTTPError as exc:
        return {"name": "ollama", "ok": False, "critical": True,
                "detail": f"недосяжний ({type(exc).__name__}) @ {url}"}


def check_sandbox(*, which: Callable[[str], str | None] = shutil.which) -> dict[str, object]:
    """bwrap для code_exec. Критичний лише коли одночасно code_exec увімкнено
    і require_sandbox — інакше відсутність bwrap не блокує роботу."""
    has_bwrap = which("bwrap") is not None
    strict = bool(settings.enable_code_exec and settings.code_exec_require_sandbox)
    ok = has_bwrap or not strict
    detail = "bwrap є" if has_bwrap else (
        "bwrap відсутній — code_exec fail-closed відхилятиме" if strict else "bwrap відсутній (не критично)"
    )
    return {"name": "sandbox:bwrap", "ok": ok, "critical": strict, "detail": detail}


def check_env(required: tuple[str, ...]) -> list[dict[str, object]]:
    """Наявність критичних значень у Settings (порожній рядок = не задано)."""
    out: list[dict[str, object]] = []
    for name in required:
        val = str(getattr(settings, name.lower(), "") or "").strip()
        out.append({"name": f"env:{name}", "ok": bool(val), "critical": True,
                    "detail": "задано" if val else "порожнє"})
    return out


def run_doctor(
    *,
    client: httpx.Client | None = None,
    services: tuple[tuple[str, str, bool], ...] = _SERVICES,
    require_env: tuple[str, ...] = (),
    which: Callable[[str], str | None] = shutil.which,
) -> list[dict[str, object]]:
    own = client is None
    cl = client or httpx.Client()
    try:
        results: list[dict[str, object]] = [
            check_service(name, url, critical=crit, client=cl) for name, url, crit in services
        ]
        results.append(check_ollama(cl))
        results.append(check_sandbox(which=which))
        results.extend(check_env(require_env))
        return results
    finally:
        if own:
            cl.close()


def summarize(results: list[dict[str, object]]) -> tuple[bool, str]:
    """`(healthy, report)` — healthy=False, якщо провалився хоч один critical-чек."""
    lines: list[str] = []
    healthy = True
    for r in results:
        crit = bool(r.get("critical"))
        ok = bool(r.get("ok"))
        if crit and not ok:
            healthy = False
        mark = "✅" if ok else ("❌" if crit else "⚠️")
        lines.append(f"{mark} {str(r['name']):<22} {r.get('detail', '')}")
    lines.append("healthy" if healthy else "UNHEALTHY (критичний чек провалено)")
    return healthy, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis-doctor", description="Діагностика JARVIS-стека")
    ap.add_argument("--json", action="store_true", help="машинний вивід")
    args = ap.parse_args(argv)
    results = run_doctor()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        healthy = all(r.get("ok") for r in results if r.get("critical"))
    else:
        healthy, report = summarize(results)
        print(report)
    return 0 if healthy else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
