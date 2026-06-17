"""Skills library (P7) — `data/skills/*/SKILL.md` + active skill у Redis."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .config import settings
from .redis_util import get_redis

logger = logging.getLogger("jarvis.tools.skills")

_KEY = "jarvis:skill:"
_SKILL_FILE = "SKILL.md"
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _skills_root() -> Path:
    return Path(settings.data_dir) / "skills"


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw.strip()
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    body = raw[m.end() :].strip()
    return meta, body


def _tags_of(meta: dict[str, str]) -> list[str]:
    """Теги скіла з frontmatter `tags: a, b`. `apk` позначає скіл, що задіює функції смартфона."""
    raw = meta.get("tags") or meta.get("requires") or ""
    return [t.strip().lower() for t in raw.replace(";", ",").split(",") if t.strip()]


def _skill_card(meta: dict[str, str], body: str, sid: str) -> dict[str, Any]:
    tags = _tags_of(meta)
    return {
        "name": meta.get("name") or sid,
        "id": sid,
        "description": meta.get("description") or body[:200],
        "size": len(body),
        "tags": tags,
        "apk": "apk" in tags,  # потребує доступу APK до функцій телефона
    }


def list_skills() -> list[dict[str, Any]]:
    root = _skills_root()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            skill_file = entry / _SKILL_FILE
            if skill_file.is_file():
                meta, body = _parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
                out.append(_skill_card(meta, body, entry.name))
        elif entry.suffix.lower() == ".md":
            meta, body = _parse_frontmatter(entry.read_text(encoding="utf-8", errors="replace"))
            out.append(_skill_card(meta, body, entry.stem))
    return out


def get_skill(skill_id: str) -> dict[str, Any] | None:
    skill_id = (skill_id or "").strip()
    if not skill_id or ".." in skill_id or "/" in skill_id or "\\" in skill_id:
        return None
    root = _skills_root()
    path = root / skill_id / _SKILL_FILE
    if not path.is_file():
        path = root / f"{skill_id}.md"
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(raw)
    cap = settings.skills_max_chars
    if len(body) > cap:
        body = body[:cap] + "\n…[truncated]"
    return {
        "id": skill_id,
        "name": meta.get("name") or skill_id,
        "description": meta.get("description") or "",
        "content": body,
        "meta": meta,
    }


async def active_skill_id(user_id: int) -> str | None:
    try:
        raw = await get_redis().get(f"{_KEY}{int(user_id)}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("active skill read failed: %s", exc)
        return None
    if not raw:
        return None
    return str(raw).strip() or None


async def set_active_skill(user_id: int, skill_id: str | None) -> None:
    r = get_redis()
    key = f"{_KEY}{int(user_id)}"
    try:
        if not skill_id:
            await r.delete(key)
        else:
            await r.set(key, skill_id.strip())
    except Exception as exc:  # noqa: BLE001
        logger.warning("active skill set failed: %s", exc)


async def resolve_skill_block(user_id: int) -> str:
    sid = await active_skill_id(user_id)
    if not sid:
        return ""
    skill = get_skill(sid)
    if not skill:
        await set_active_skill(user_id, None)
        return ""
    return skill_prompt_block(skill)


def skill_prompt_block(skill: dict[str, Any]) -> str:
    name = str(skill.get("name") or skill.get("id") or "").strip()
    content = str(skill.get("content") or "").strip()
    if not content:
        return ""
    return f" Активний skill «{name}»:\n{content}"
