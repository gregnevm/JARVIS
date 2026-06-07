"""LLM-as-judge для eval harness (Фаза 3 C.3): Ollama оцінює якість відповіді."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

_USER_ROLES = frozenset({"user", "human", "from"})
_ASST_ROLES = frozenset({"assistant", "gpt", "bot"})

_JUDGE_PROMPT = """You are an evaluation judge for a personal AI assistant training dataset.
Decide if the assistant reply is on-topic, helpful, and reasonable for the user message.
Reply with exactly one line starting with PASS or FAIL, optionally followed by ": reason".

User:
{user}

Assistant:
{assistant}
"""


def extract_turns(row: dict[str, Any]) -> tuple[str, str] | None:
    conv = row.get("conversations") or row.get("messages")
    if not conv or not isinstance(conv, list):
        return None
    user_parts: list[str] = []
    asst_parts: list[str] = []
    for msg in conv:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or msg.get("from") or "").lower()
        text = str(msg.get("content") or msg.get("value") or "").strip()
        if not text:
            continue
        if role in _USER_ROLES:
            user_parts.append(text)
        elif role in _ASST_ROLES:
            asst_parts.append(text)
    if not user_parts or not asst_parts:
        return None
    return user_parts[-1], asst_parts[-1]


def parse_verdict(text: str) -> tuple[bool, str]:
    line = (text or "").strip().splitlines()[0] if text else ""
    upper = line.upper()
    if upper.startswith("PASS"):
        reason = line[4:].lstrip(": ").strip()
        return True, reason or "pass"
    if upper.startswith("FAIL"):
        reason = line[4:].lstrip(": ").strip()
        return False, reason or "fail"
    if re.search(r"\bPASS\b", upper):
        return True, line
    if re.search(r"\bFAIL\b", upper):
        return False, line
    return False, f"unparseable verdict: {line[:120]}"


def ollama_judge(
    user: str,
    assistant: str,
    *,
    ollama_url: str,
    model: str,
    timeout: float = 120.0,
) -> tuple[bool, str]:
    host = ollama_url.rstrip("/")
    prompt = _JUDGE_PROMPT.format(user=user.strip(), assistant=assistant.strip())
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 64},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        return False, f"ollama http {exc.code}: {body}"
    except Exception as exc:  # noqa: BLE001
        return False, f"ollama error: {exc}"
    msg = data.get("message")
    content = str(msg.get("content", "")) if isinstance(msg, dict) else ""
    return parse_verdict(content)


def judge_row(
    row: dict[str, Any],
    *,
    ollama_url: str,
    model: str,
    timeout: float = 120.0,
) -> tuple[bool, str]:
    turns = extract_turns(row)
    if not turns:
        return False, "missing user/assistant turns"
    user, assistant = turns
    return ollama_judge(user, assistant, ollama_url=ollama_url, model=model, timeout=timeout)
