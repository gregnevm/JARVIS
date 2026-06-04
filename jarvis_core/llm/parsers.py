from __future__ import annotations

import json


def kobold_token(line: str) -> str:
    line = line.strip()
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line or line == "[DONE]":
        return ""
    try:
        return str(json.loads(line).get("token", ""))
    except json.JSONDecodeError:
        return ""


def ollama_chunk(line: str) -> tuple[str, bool]:
    line = line.strip()
    if not line:
        return "", False
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return "", False
    return str(data.get("response", "")), bool(data.get("done"))


def ollama_chat_chunk(line: str) -> tuple[str, bool]:
    """Розбирає NDJSON-рядок стріму /api/chat → (delta-контент, done).

    Кожен рядок: {"message":{"role":"assistant","content":"<кусок>"},"done":false}.
    Фінальний рядок має done:true і порожній content.
    """
    line = line.strip()
    if not line:
        return "", False
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return "", False
    msg = data.get("message")
    content = str(msg.get("content", "")) if isinstance(msg, dict) else ""
    return content, bool(data.get("done"))
