"""Health watch alerts."""
import asyncio

from app.health_watch import check_and_alert


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, val):
        self.data[key] = val


class FakeTG:
    sent = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


class FakeSvc:
    def __init__(self, dash):
        self._dash = dash

    async def dashboard(self):
        return self._dash


def _run(coro):
    return asyncio.run(coro)


def test_health_alert_on_transition():
    redis = FakeRedis()
    tg = FakeTG()
    svc = FakeSvc({"ollama_up": True, "hostagent_up": True, "docker_up": True})
    _run(check_and_alert(redis, tg, svc, alert_ids={1}))
    assert not tg.sent
    svc._dash = {"ollama_up": False, "hostagent_up": True, "docker_up": True}
    _run(check_and_alert(redis, tg, svc, alert_ids={1}))
    assert tg.sent
    assert "Ollama" in tg.sent[0][1]
