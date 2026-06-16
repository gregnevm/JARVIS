"""No-progress детектор для test-fix циклу (Стовп B / CA-3.4).

Stop-condition «однаковий fail двічі». Коли `run_tests` повертає той самий набір
впалих тестів (та сама сигнатура) поспіль, ReAct-луп ризикує крутитися без
прогресу — однакова правка → однаковий fail. Тут — легкий трекер останньої
сигнатури на user (Redis, коротка TTL), що повертає підказку моделі «зміни
підхід або зупинись і чесно звітуй», коли fail повторюється.

Стан минущий (сесійний): TTL коротка, key per-user. PASS або новий набір впалих
тестів — скидає лічильник. Redis недоступний → no-op (graceful), раннер не валимо.
"""
from __future__ import annotations

import hashlib
import re

from ..redis_util import get_redis

_KEY = "ca:fixloop:lastfail:{uid}"
_TTL = 1800  # 30 хв — вікно одного fix-циклу
_PROMPT = (
    "\n\n⚠️ Немає прогресу: ідентичний набір впалих тестів уже {n}-й раз поспіль. "
    "Зміни підхід (інша гіпотеза / інший файл) або зупинись і чесно звітуй, де "
    "застряг — не повторюй ту саму правку."
)


def fail_signature(parts: list[str]) -> str:
    """Стабільна коротка сигнатура fail-стану (sha1-hex, без ':')."""
    raw = "|".join(p for p in parts if p)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def summary_signature(summary: str) -> str:
    """Сигнатура з рендереного підсумку run_tests (для fix-orchestration CA-3.2).

    Орієнтир — список впалих тестів (рядки з відступом до роздільника '---').
    Якщо імен нема (generic-раннер) — хеш голови підсумку. Стабільне до timing/
    no-progress-підказки, бо дивиться лише на набір впалих тестів.
    """
    head = summary.split("\n---", 1)[0]
    names = re.findall(r"^\s{2}(\S+)$", head, re.MULTILINE)
    basis = sorted(set(names)) if names else [head.strip()[:200]]
    return fail_signature(basis)


def _parse(raw: bytes | str | None) -> tuple[str, int]:
    """'<n>:<sig>' → (sig, n). Сигнатура — hex (без ':'), тож partition безпечний."""
    if not raw:
        return "", 0
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    n_str, _, sig = s.partition(":")
    try:
        return sig, int(n_str)
    except ValueError:
        return sig, 0


async def note_test_result(user_id: int, *, ok: bool, signature: str) -> str:
    """Оновлює стан і повертає no-progress-підказку (або '').

    - PASS або порожня сигнатура → скидаємо лічильник, повертаємо ''.
    - Той самий fail вдруге+ поспіль → інкремент і підказка моделі.
    - Інший fail → лічильник = 1, без підказки.
    """
    if user_id <= 0:
        return ""
    key = _KEY.format(uid=user_id)
    try:
        r = get_redis()
        if ok or not signature:
            await r.delete(key)
            return ""
        prev_sig, prev_n = _parse(await r.get(key))
        n = prev_n + 1 if prev_sig == signature else 1
        await r.setex(key, _TTL, f"{n}:{signature}")
        return _PROMPT.format(n=n) if n >= 2 else ""
    except Exception:  # noqa: BLE001 — стан минущий, раннер важливіший за трекер
        return ""
