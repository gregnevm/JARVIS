from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Витягує JSON-об'єкт з відповіді LLM (markdown fence або сирий JSON)."""
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


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


def ollama_chat_chunk(line: str) -> tuple[str, bool, dict[str, Any] | None]:
    """Розбирає NDJSON-рядок стріму /api/chat → (delta, done, stats|None).

    Фінальний рядок: done:true + eval_count/eval_duration для tok/s.
    """
    line = line.strip()
    if not line:
        return "", False, None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return "", False, None
    msg = data.get("message")
    content = str(msg.get("content", "")) if isinstance(msg, dict) else ""
    done = bool(data.get("done"))
    stats = ollama_inference_stats(data) if done else None
    return content, done, stats


def ollama_inference_stats(data: dict[str, Any]) -> dict[str, Any] | None:
    """eval_count / eval_duration (ns) з відповіді Ollama /api/chat."""
    try:
        ec = int(data.get("eval_count") or 0)
        ed = int(data.get("eval_duration") or 0)
    except (TypeError, ValueError):
        return None
    if ec <= 0 or ed <= 0:
        return None
    return {
        "eval_count": ec,
        "eval_duration_ns": ed,
        "model": str(data.get("model") or ""),
    }
