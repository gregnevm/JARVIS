import asyncio

from app.bot.commands import is_command


def test_is_command():
    assert is_command("/start")
    assert is_command("/mode agent")
    assert not is_command("привіт")


def test_start_skips_agent(monkeypatch):
    from app import router
    from app.config import settings

    class TG:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
            self.sent.append(text)

        async def answer_callback_query(self, *_):
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
        async def allow(self, user_id: int) -> bool:
            return True

    class STT:
        async def transcribe(self, audio, filename="voice.ogg"):
            return ""

    monkeypatch.setattr(settings, "allowed_user_ids", "42")

    async def _run():
        tg = TG()
        class Rds:
            async def get(self, k):
                return None

            async def setex(self, k, t, v):
                pass

            async def delete(self, *k):
                pass

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
    assert any("Dashboard" in s or "JARVIS" in s for s in tg.sent)
