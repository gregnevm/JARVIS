"""Реєстр команд (`bot/dispatch.py`) — Ctx-парсинг + єдине джерело правди про команди."""
from __future__ import annotations

from app.bot.commands import is_command, registry
from app.bot.dispatch import CommandRegistry, Ctx


def _ctx(text: str) -> Ctx:
    return Ctx(text=text, chat_id=1, user_id=2, tg=None, svc=None)  # type: ignore[arg-type]


def test_ctx_parsing():
    c = _ctx("/project new Робота Дім")
    assert c.cmd == "/project"
    assert c.args == "new Робота Дім"
    assert c.arg_list == ["new", "робота", "дім"]


def test_ctx_normalizes_cmd_with_botname():
    assert _ctx("/Mode@JarvisBot agent").cmd == "/mode"
    assert _ctx("").cmd == ""


def test_previously_unreachable_commands_now_registered():
    # Регресія: /login, /plan, /improve випадали з COMMANDS і `is_command` їх не бачив.
    for cmd in ("/login", "/plan", "/improve", "/connect"):
        assert registry.has(cmd), cmd
        assert is_command(cmd), cmd


def test_is_command_still_rejects_plain_text():
    assert not is_command("привіт")
    assert not is_command("just text")


def test_menu_commands_only_menu_flagged():
    names = {c["command"] for c in registry.menu_commands()}
    assert "connect" in names
    assert "start" in names
    # admin-only утиліти не в швидкому меню
    assert "dataset" not in names
    assert "improve" not in names


def test_registry_decorator_and_aliases():
    reg = CommandRegistry()
    calls: list[str] = []

    @reg.command("/foo", description="d", menu=True, aliases=("/f",))
    async def _h(ctx: Ctx) -> bool:
        calls.append(ctx.cmd)
        return True

    assert reg.has("/foo") and reg.has("/f")
    assert reg.get("/f") is reg.get("/foo")
    assert reg.menu_commands() == [{"command": "foo", "description": "d"}]
    # дублів-аліасів немає у specs()
    assert len(reg.specs()) == 1
