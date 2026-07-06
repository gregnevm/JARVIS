import asyncio

from app.bot.commands import is_command
from app.bot.keyboards import (
    BTN_STATUS,
    main_menu_keyboard,
    mode_keyboard,
    remove_reply_keyboard,
    reply_keyboard,
)
from app.bot.quick_actions import is_quick_action


def test_is_command():
    assert is_command("/start")
    assert is_command("/brief")
    assert is_command("/reminders")
    assert is_command("/keyboard")
    assert is_command("/mode agent")
    assert is_command("/app")
    assert not is_command("привіт")


def test_is_quick_action():
    assert is_quick_action(BTN_STATUS)
    assert not is_quick_action("привіт")


def test_reply_keyboard_structure():
    kb = reply_keyboard()
    assert kb["resize_keyboard"] is True
    assert kb["is_persistent"] is True
    assert any(row[0]["text"] == BTN_STATUS for row in kb["keyboard"])


def test_remove_reply_keyboard():
    assert remove_reply_keyboard() == {"remove_keyboard": True}


def test_mode_keyboard_has_computer():
    rows = mode_keyboard()["inline_keyboard"]
    flat = [btn["callback_data"] for row in rows for btn in row]
    assert "mode:computer" in flat


def test_main_menu_has_brief_and_reminders():
    rows = main_menu_keyboard()["inline_keyboard"]
    flat = [btn.get("callback_data") for row in rows for btn in row]
    assert "dash:brief" in flat
    assert "dash:reminders" in flat


def test_start_skips_agent(monkeypatch):
    from app import router
    from app.config import settings

    class TG:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
            self.sent.append((text, reply_markup))

        async def edit_message_text(self, *a, **kw):
            pass

        async def answer_callback_query(self, *_a, **_kw):
            pass

    class Tools:
        calls = []

        async def process(self, p):
            Tools.calls.append(p)
            return "agent"

    class Svc:
        async def dashboard(self):
            return {"agent_mode": "hybrid", "ollama_up": True}

        async def set_mode(self, m):
            return {"mode": m}

        async def twin_status(self):
            return {}

    class Lim:
        async def allow(self, user_id: int, *, limit: int | None = None) -> bool:
            return True

    class STT:
        async def transcribe(self, audio, filename="voice.ogg"):
            return ""

    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "telegram_reply_keyboard", True)

    async def _run():
        tg = TG()

        class Rds:
            def __init__(self) -> None:
                self.kv: dict[str, str] = {}

            async def get(self, k):
                return self.kv.get(k)

            async def set(self, k, v, nx=False, ex=None):
                if nx and k in self.kv:
                    return None
                self.kv[k] = v
                return True

            async def setex(self, k, t, v):
                self.kv[k] = v

            async def delete(self, *k):
                for key in k:
                    self.kv.pop(key, None)

            async def zrange(self, *a, **k):
                return []

        await router.handle_update(
            {"message": {"from": {"id": 42}, "chat": {"id": 5}, "text": "/start"}},
            tg,
            Tools(),
            Svc(),
            STT(),
            Lim(),
            Rds(),
        )
        return tg

    tg = asyncio.run(_run())
    assert Tools.calls == []
    assert any("JARVIS" in s[0] for s in tg.sent)
    assert any(s[1] and "keyboard" in s[1] for s in tg.sent)


class _TgAuthRedis:
    """Fake redis mirroring production semantics (decode_responses=True → str values)."""

    def __init__(self, kv: dict[str, str] | None = None) -> None:
        self.kv: dict[str, str] = dict(kv or {})
        self.ttls: dict[str, int] = {}

    async def get(self, k):
        return self.kv.get(k)

    async def setex(self, k, t, v):
        self.kv[k] = v
        self.ttls[k] = t


def test_bind_tgauth_login_arms_pending_token():
    from app.bot.commands import bind_tgauth_login

    async def _run():
        r = _TgAuthRedis({"tgauth:tok1": "pending"})
        assert await bind_tgauth_login(r, "tok1", 42) is True
        assert r.kv["tgauth:tok1"] == "42"  # bound to the confirming uid
        assert r.ttls["tgauth:tok1"] == 300  # arming (re)sets the 5-min redeem window

    asyncio.run(_run())


def test_bind_tgauth_login_rejects_unminted_replayed_and_clobber():
    from app.bot.commands import bind_tgauth_login

    async def _run():
        # attacker-CHOSEN token the server never minted (arbitrary ?start=tgauth_<x> deeplink):
        # rejected, no key created. NOTE: this closes only the unminted variant — an attacker who
        # MINTS their own pending token then phishes the victim is a separate residual (see the
        # bind_tgauth_login docstring), not fixed here.
        r1 = _TgAuthRedis()
        assert await bind_tgauth_login(r1, "evil", 42) is False
        assert "tgauth:evil" not in r1.kv
        # already bound to another uid: first-confirm-wins, no clobber
        r2 = _TgAuthRedis({"tgauth:t": "7"})
        assert await bind_tgauth_login(r2, "t", 42) is False
        assert r2.kv["tgauth:t"] == "7"
        # consumed/expired token (absent after /poll delete): no resurrection
        r3 = _TgAuthRedis()
        assert await bind_tgauth_login(r3, "gone", 42) is False
        assert "tgauth:gone" not in r3.kv

    asyncio.run(_run())


def test_cmd_start_tgauth_arms_only_pending_and_messages():
    from app.bot.commands import _cmd_start
    from app.bot.dispatch import Ctx

    class TG:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append(text)

    async def _run():
        # pending token → armed, success message
        tg1, r1 = TG(), _TgAuthRedis({"tgauth:good": "pending"})
        ctx1 = Ctx(text="/start tgauth_good", chat_id=5, user_id=42, tg=tg1, svc=object(), redis=r1)
        assert await _cmd_start(ctx1) is True
        assert r1.kv["tgauth:good"] == "42"
        assert any("підтверджено" in s for s in tg1.sent)

        # attacker-chosen unminted token → NOT armed, user told the link is invalid
        tg2, r2 = TG(), _TgAuthRedis()
        ctx2 = Ctx(text="/start tgauth_evil", chat_id=5, user_id=42, tg=tg2, svc=object(), redis=r2)
        assert await _cmd_start(ctx2) is True
        assert "tgauth:evil" not in r2.kv
        assert any("недійсне" in s for s in tg2.sent)

        # empty token (?start=tgauth_) → guard short-circuits, nothing armed, invalid message
        tg3, r3 = TG(), _TgAuthRedis()
        ctx3 = Ctx(text="/start tgauth_", chat_id=5, user_id=42, tg=tg3, svc=object(), redis=r3)
        assert await _cmd_start(ctx3) is True
        assert r3.kv == {}
        assert any("недійсне" in s for s in tg3.sent)

    asyncio.run(_run())


def test_quick_status_skips_agent(monkeypatch):
    from app import router
    from app.config import settings

    class TG:
        calls = []

        async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
            self.calls.append(text)

        async def send_chat_action(self, *a, **kw):
            pass

    class Tools:
        calls = []

        async def process(self, p):
            Tools.calls.append(p)
            return "agent"

    class Svc:
        async def dashboard(self):
            return {"agent_mode": "hybrid", "ollama_up": True}

        async def twin_status(self):
            return {}

    class Lim:
        async def allow(self, user_id: int, *, limit: int | None = None) -> bool:
            return True

    monkeypatch.setattr(settings, "allowed_user_ids", "42")

    async def _run():
        await router.handle_update(
            {
                "message": {
                    "from": {"id": 42},
                    "chat": {"id": 5},
                    "text": BTN_STATUS,
                }
            },
            TG(),
            Tools(),
            Svc(),
            None,
            Lim(),
            None,
        )

    asyncio.run(_run())
    assert Tools.calls == []
