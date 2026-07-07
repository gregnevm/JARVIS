from __future__ import annotations

import json
import re
from typing import Any


def scan_balanced_json(s: str, start: int) -> tuple[str | None, int]:
    """Від `{` у s[start] повертає (підрядок збалансованого об'єкта, індекс після нього).

    Поважає рядкові літерали та екранування, тож дужки всередині рядкових значень
    (напр. ``"a{b}c"``) не ламають баланс. Якщо об'єкт незакритий → (None, start).
    SSOT балансованого сканера (реюзається агент-лупом для inline tool-calls).
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1], i + 1
    return None, start


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Витягує JSON-об'єкт з відповіді LLM (markdown fence або сирий JSON).

    Стійко до прози з дужками до/після JSON: сканує збалансований об'єкт від
    КОЖНОГО `{` і повертає перший, що парситься в dict. Старий `rfind('}')`
    хапав дужку з хвостової прози ("{...} note: use } carefully") і мовчки
    повертав None (тихий degrade плану/рев'ю на 7B-моделі).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else raw
    idx = candidate.find("{")
    while idx >= 0:
        obj, end = scan_balanced_json(candidate, idx)
        if obj is None:
            # Незакрита дужка від idx: усе далі — на глибині ≥1 цього об'єкта,
            # тож жоден пізніший старт не дасть top-level об'єкт. Стоп (лінійно).
            break
        try:
            data = json.loads(obj)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data
        # Збалансований, але не валідний JSON (напр. хвостова кома чи `{options}`
        # з прози) → пропускаємо ВЕСЬ об'єкт, не лізем у його нутрощі (інакше
        # діставали б вкладений під-об'єкт малформед-outer'а й глушили фолбек).
        idx = candidate.find("{", end)
    return None


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


def openai_delta(line: str) -> tuple[str, bool]:
    """SSE-рядок OpenAI-сумісного /v1/chat/completions → (delta, done).

    Формат: `data: {json}` з `choices[0].delta.content`; термінатор `data: [DONE]`.
    SSOT парсингу для будь-якого OpenAI-сумісного бекенда (OpenAICompatAdapter)."""
    line = line.strip()
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line:
        return "", False
    if line == "[DONE]":
        return "", True
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return "", False
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return "", False
    delta = choices[0].get("delta") or {}
    content = str(delta.get("content") or "") if isinstance(delta, dict) else ""
    return content, bool(choices[0].get("finish_reason"))


def ollama_inference_stats(data: dict[str, Any]) -> dict[str, Any] | None:
    """eval_count / eval_duration (ns) з відповіді Ollama /api/chat.

    Додатково (SY-6, адитивно): `prompt_eval_count` — вхідні токени (0, якщо
    Ollama їх не віддав) — для usage-паспортів tokens-in/out."""
    try:
        ec = int(data.get("eval_count") or 0)
        ed = int(data.get("eval_duration") or 0)
        pec = int(data.get("prompt_eval_count") or 0)
    except (TypeError, ValueError):
        return None
    if ec <= 0 or ed <= 0:
        return None
    return {
        "eval_count": ec,
        "eval_duration_ns": ed,
        "prompt_eval_count": max(0, pec),
        "model": str(data.get("model") or ""),
    }
