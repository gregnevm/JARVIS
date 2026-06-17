#!/usr/bin/env python3
"""jarvis_context — мінімальний колектор контексту (Стовп C / CL-3, культура P9/P10).

Ллє паспорт контексту в JARVIS уже зараз — без APK, без залежностей (лише stdlib).
Будь-яке джерело: ручна нотатка, pipe, гарячa клавіша, Task Scheduler/cron.

Потрібно на сервері: `ENABLE_CONTEXT_API=true` + `PLATFORM_PASSWORD` (Basic) або JWT.

Приклади:
  python scripts/jarvis_context.py "Домовився з Орестом про зустріч у пʼятницю" \\
      --kind note --tags person:orest,topic:meeting

  git log --oneline -5 | python scripts/jarvis_context.py --kind worklog \\
      --source git --tags project:jarvis

  python scripts/jarvis_context.py --search "коли зустріч з Орестом"

Env (фолбек для прапорів):
  JARVIS_URL            (default http://127.0.0.1:8000)
  JARVIS_USER           (default admin)
  JARVIS_PASSWORD       Basic-пароль = PLATFORM_PASSWORD
  JARVIS_TOKEN          JWT access-токен (має пріоритет над Basic)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request


def _auth_header(args: argparse.Namespace) -> tuple[str, str]:
    token = args.token or os.environ.get("JARVIS_TOKEN", "")
    if token:
        return "Authorization", f"Bearer {token}"
    user = args.user or os.environ.get("JARVIS_USER", "admin")
    password = args.password or os.environ.get("JARVIS_PASSWORD", "")
    if not password:
        sys.exit("error: no auth — set --password / JARVIS_PASSWORD (PLATFORM_PASSWORD) or --token / JARVIS_TOKEN")
    raw = f"{user}:{password}".encode()
    return "Authorization", "Basic " + base64.b64encode(raw).decode()


def _post(url: str, path: str, body: dict, auth: tuple[str, str]) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", auth[0]: auth[1]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        sys.exit(f"error: HTTP {exc.code} — {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: cannot reach {url} — {exc.reason}")


def main() -> None:
    p = argparse.ArgumentParser(description="JARVIS context collector (P9/P10)")
    p.add_argument("summary", nargs="?", help="текст-summary події (або читається зі stdin)")
    p.add_argument("--content", help="сире наповнення (фолбек для summary)")
    p.add_argument("--kind", default="note", help="тип паспорта (note|call|sms|worklog|daily…)")
    p.add_argument("--tags", default="", help="namespaced-теги через кому: person:mom,topic:rent")
    p.add_argument("--source", default="cli", help="джерело події")
    p.add_argument("--sensitivity", default="personal", help="public|personal|health|finance")
    p.add_argument("--event-id", help="клієнтський id для ідемпотентності")
    p.add_argument("--search", metavar="QUERY", help="режим ретриву: семантичний пошук по контексту")
    p.add_argument("--recent", type=int, metavar="N", help="режим ретриву: останні N паспортів")
    p.add_argument(
        "--job",
        choices=["summarize", "daily", "retention"],
        help="тригер обслуговуючого прогону (для cron/Task Scheduler)",
    )
    p.add_argument("--url", default=os.environ.get("JARVIS_URL", "http://127.0.0.1:8000"))
    p.add_argument("--user")
    p.add_argument("--password")
    p.add_argument("--token")
    args = p.parse_args()
    auth = _auth_header(args)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if args.job:
        out = _post(args.url, f"/api/v1/context/jobs/context_{args.job}", {}, auth)
        print(json.dumps(out, ensure_ascii=False))
        return

    if args.search:
        out = _post(args.url, "/api/v1/context/search",
                    {"query": args.search, "tags": tags or None}, auth)
        for r in out.get("results", []):
            score = r.get("score")
            prefix = f"[{score:.2f}] " if isinstance(score, (int, float)) else ""
            print(f"{prefix}{r.get('summary','')}  {r.get('tags',[])}")
        return

    if args.recent is not None:
        out = _post(args.url, "/api/v1/context/recent",
                    {"limit": args.recent, "tags": tags or None}, auth)
        for r in out.get("events", []):
            print(f"{r.get('created_at','')}  {r.get('summary','')}  {r.get('tags',[])}")
        return

    # Інакше — ingest. summary з аргументу або stdin.
    summary = args.summary
    if not summary and not sys.stdin.isatty():
        summary = sys.stdin.read().strip()
    if not summary and not args.content:
        sys.exit("error: nothing to ingest — give summary text, --content, or pipe via stdin")

    event = {
        "kind": args.kind, "summary": summary, "content": args.content,
        "tags": tags, "source": args.source, "sensitivity": args.sensitivity,
    }
    if args.event_id:
        event["event_id"] = args.event_id
    out = _post(args.url, "/api/v1/ingest/events", {"events": [event]}, auth)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
