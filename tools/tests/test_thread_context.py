"""build_thread_context — формат короткого контексту треду з Memory.

До цього проходу модуль `app/thread_context.py` (активно використовується в
`agent.py::_build_messages` для C0 chat-контексту) не мав ЖОДНОГО прямого
тесту — ні юніт-, ні інтеграційного. Покриваємо основні гілки: порожню
історію, тегування ролей, обрізання окремого повідомлення (`_MAX_MSG`),
обрізання сумарної довжини (`_MAX_TOTAL`) та пропуск порожніх реплік.
"""
from __future__ import annotations

from typing import Any

from app.thread_context import _MAX_MSG, _MAX_TOTAL, build_thread_context


class FakeMemory:
    def __init__(self, msgs: list[dict[str, Any]]) -> None:
        self._msgs = msgs

    async def history(self, user_id: int, limit: int = 12) -> list[dict[str, Any]]:
        return self._msgs[-limit:]


async def test_empty_history_returns_empty_string():
    out = await build_thread_context(FakeMemory([]), 1)
    assert out == ""


async def test_formats_and_tags_roles():
    mem = FakeMemory(
        [
            {"role": "user", "content": "привіт"},
            {"role": "assistant", "content": "вітаю!"},
            {"role": "system", "content": "контекст"},
        ]
    )
    out = await build_thread_context(mem, 1)
    assert out.startswith(" Останні репліки: ")
    assert "U: привіт" in out
    assert "A: вітаю!" in out
    assert "s: контекст" in out  # невідома роль → перша літера


async def test_skips_empty_bodies_and_strips_newlines():
    mem = FakeMemory(
        [
            {"role": "user", "content": "   "},
            {"role": "user", "content": "рядок1\nрядок2"},
        ]
    )
    out = await build_thread_context(mem, 1)
    assert "U: рядок1 рядок2" in out
    assert out.count("U:") == 1  # порожнє повідомлення пропущене


async def test_all_empty_bodies_returns_empty_string():
    mem = FakeMemory([{"role": "user", "content": "   "}, {"role": "user", "content": ""}])
    assert await build_thread_context(mem, 1) == ""


async def test_truncates_individual_message_to_max_msg():
    long_body = "x" * (_MAX_MSG + 50)
    mem = FakeMemory([{"role": "user", "content": long_body}])
    out = await build_thread_context(mem, 1)
    # "U: " + щонайбільше _MAX_MSG символів тіла
    assert len(out.split("U: ", 1)[1]) <= _MAX_MSG


async def test_stops_once_total_budget_exceeded():
    # Кожне повідомлення ~ _MAX_MSG символів; разом точно перевищать _MAX_TOTAL,
    # тож build_thread_context має зупинитись раніше, ніж включить усі.
    n = (_MAX_TOTAL // _MAX_MSG) + 3
    msgs = [{"role": "user", "content": f"msg{i} " + "y" * (_MAX_MSG - 6)} for i in range(n)]
    mem = FakeMemory(msgs)
    out = await build_thread_context(mem, n)
    assert out.count("U:") < n
    assert len(out) < _MAX_TOTAL + len(" Останні репліки: ") + _MAX_MSG


async def test_respects_history_limit_argument():
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    mem = FakeMemory(msgs)
    out = await build_thread_context(mem, 1, limit=3)
    assert "m17" in out and "m18" in out and "m19" in out
    assert "m16" not in out
