"""R4 «Тонкий шлюз» — code-first інвентар env-змінних + drift-гейт (D1 машиною).

Джерело правди — Settings-класи сервісів (gateway/tools/memory/twin/hostagent).
Скрипт:

  1. знімає інвентар полів кожного сервісу (окремий підпроцес на сервіс — три
     пакети `app` не живуть в одному процесі);
  2. пише по-сервісні снапшоти `<svc>/tests/data/env_snapshot.json` — їх
     перевіряють снапшот-тести (контракт «env-імена й дефолти незмінні», S2);
  3. генерує зведену таблицю змінних у docs/ENV_CHECKLIST.md між GEN-маркерами;
  4. `--check` (CI drift-гейт): згенероване ≠ закомічене → exit 1; плюс
     `.env.example` не містить змінних, невідомих жодному Settings (stale-гейт).

Запуск: `python scripts/gen_env_docs.py` (оновити файли) або `--check` (CI).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ("gateway", "tools", "memory", "twin", "hostagent", "tts")
CHECKLIST = ROOT / "docs" / "ENV_CHECKLIST.md"
ENV_EXAMPLE = ROOT / ".env.example"
GEN_BEGIN = "<!-- GEN:ENV-INVENTORY:BEGIN (scripts/gen_env_docs.py — не редагуй руками) -->"
GEN_END = "<!-- GEN:ENV-INVENTORY:END -->"

# Змінні поза Settings-класами: інтерполяція docker-compose, тулінг, CI.
# Додаючи сюди — лиши коментар навіщо вона.
EXTRA_KNOWN: dict[str, str] = {
    "COMPOSE_PROJECT_NAME": "docker compose",
    "TELEGRAM_BOT_TOKEN_FILE": "secret-файл варіант токена (compose)",
    "CLOUDFLARE_TUNNEL_TOKEN": "compose: cloudflared named tunnel",
    "ENABLE_QUICK_TUNNEL": "compose/scripts: ефемерний quick-tunnel",
    "GENERIC_TIMEZONE": "compose: TZ контейнерів",
    "TZ": "compose: TZ контейнерів",
    "WHISPER_MODEL": "compose: готовий whisper-образ (env напряму)",
    "N8N_BASIC_AUTH_ACTIVE": "compose: legacy n8n (кандидат на видалення)",
    "N8N_BASIC_AUTH_USER": "compose: legacy n8n (кандидат на видалення)",
    "N8N_BASIC_AUTH_PASSWORD": "compose: legacy n8n (кандидат на видалення)",
    "CONTINUE_API_KEY": "scripts/setup_continue.ps1 (IDE-інтеграція)",
}


def _inspect_child(svc: str) -> dict[str, str]:
    """Інвентар одного сервісу в підпроцесі (ізоляція пакета `app`)."""
    out = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--inspect", svc],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=True,
    )
    data = json.loads(out.stdout)
    assert isinstance(data, dict)
    return data


def _inspect_here(svc: str) -> dict[str, str]:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(1, str(ROOT / svc))
    import app.config as cfg  # noqa: PLC0415 — сервісний пакет після path-манпуляції

    from jarvis_core.settings.inventory import settings_inventory

    return settings_inventory(cfg.Settings)


def collect() -> dict[str, dict[str, str]]:
    return {svc: _inspect_child(svc) for svc in SERVICES}


def render_table(inv: dict[str, dict[str, str]]) -> str:
    merged: dict[str, dict[str, str]] = {}
    for svc, fields in inv.items():
        for env, default in fields.items():
            merged.setdefault(env, {})[svc] = default
    lines = [
        GEN_BEGIN,
        "",
        f"## Повний інвентар env-змінних ({len(merged)} змінних, code-first)",
        "",
        "Згенеровано з Settings-класів сервісів. Оновити: `python scripts/gen_env_docs.py`.",
        "CI (`arch-gates`) падає, якщо таблиця/снапшоти розійшлися з кодом (drift-гейт D1).",
        "",
        "| ENV | Сервіси | Дефолт |",
        "|-----|---------|--------|",
    ]
    for env in sorted(merged):
        by_svc = merged[env]
        defaults = sorted(set(by_svc.values()))
        default_s = defaults[0] if len(defaults) == 1 else " / ".join(
            f"{svc}: {d}" for svc, d in sorted(by_svc.items())
        )
        default_s = default_s.replace("|", "\\|")
        if len(default_s) > 60:
            default_s = default_s[:57] + "…"
        lines.append(f"| `{env}` | {', '.join(sorted(by_svc))} | `{default_s}` |")
    lines += ["", GEN_END]
    return "\n".join(lines)


def splice_checklist(text: str, table: str) -> str:
    if GEN_BEGIN in text and GEN_END in text:
        head, rest = text.split(GEN_BEGIN, 1)
        _, tail = rest.split(GEN_END, 1)
        return head + table + tail
    return text.rstrip() + "\n\n" + table + "\n"


def env_example_vars() -> set[str]:
    """Імена змінних у .env.example (включно закоментовані `# VAR=` плейсхолдери)."""
    pat = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=")
    out: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            out.add(m.group(1))
    return out


def run(check: bool) -> int:
    inv = collect()
    problems: list[str] = []

    # 1. по-сервісні снапшоти
    for svc, fields in inv.items():
        snap_path = ROOT / svc / "tests" / "data" / "env_snapshot.json"
        rendered = json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if check:
            on_disk = snap_path.read_text(encoding="utf-8") if snap_path.is_file() else ""
            if on_disk != rendered:
                problems.append(f"снапшот застарів: {snap_path.relative_to(ROOT)}")
        else:
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(rendered, encoding="utf-8")

    # 2. таблиця в ENV_CHECKLIST.md
    table = render_table(inv)
    current = CHECKLIST.read_text(encoding="utf-8")
    updated = splice_checklist(current, table)
    if check:
        if current != updated:
            problems.append("docs/ENV_CHECKLIST.md: GEN-секція розійшлася з кодом")
    else:
        CHECKLIST.write_text(updated, encoding="utf-8")

    # 3. stale-гейт .env.example
    known = set(EXTRA_KNOWN) | {env for fields in inv.values() for env in fields}
    stale = sorted(env_example_vars() - known)
    if stale:
        problems.append(f".env.example: невідомі змінні (нема в жодному Settings): {stale}")

    for p in problems:
        print(f"DRIFT: {p}", file=sys.stderr)
    if problems:
        print("Онови: python scripts/gen_env_docs.py (і додай у коміт)", file=sys.stderr)
    elif check:
        print("OK: env-інвентар синхронний з кодом")
    else:
        print(f"OK: оновлено снапшоти ({len(inv)} сервісів) і ENV_CHECKLIST.md")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="drift-гейт (CI): нічого не пише")
    ap.add_argument("--inspect", metavar="SVC", help="внутрішнє: інвентар одного сервісу")
    args = ap.parse_args()
    if args.inspect:
        print(json.dumps(_inspect_here(args.inspect), ensure_ascii=False, sort_keys=True))
        return 0
    return run(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
