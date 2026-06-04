"""stream_reply — плейсхолдер, edit-цикл, фіналізація, фолбек на класику."""
import asyncio

from app.streaming import _PLACEHOLDER, stream_reply


class FakeTG:
    def __init__(self, mid: int | None = 10) -> None:
        self._mid = mid
        self.sent: list[tuple[int, str]] = []
        self.edits: list[tuple[int, int, str]] = []

    async def send_message_id(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))
        return self._mid

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None):
        self.edits.append((chat_id, message_id, text))

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


class FakeTools:
    def __init__(self, events: list[dict], classic: str = "КЛАСИКА") -> None:
        self._events = events
        self._classic = classic
        self.process_calls = 0

    async def stream(self, payload):
        for ev in self._events:
            yield ev

    async def process(self, payload):
        self.process_calls += 1
        return self._classic


def _run(coro):
    return asyncio.run(coro)


def test_streams_deltas_and_finalizes():
    tg = FakeTG()
    tools = FakeTools(
        [
            {"delta": "При"},
            {"delta": "віт"},
            {"done": True, "text": "Привіт", "mode": "chat", "iters": 0},
        ]
    )
    out = _run(stream_reply(tg, tools, 5, {"user_id": 1, "text": "привіт"}))
    assert out == "Привіт"
    assert tg.sent[0] == (5, _PLACEHOLDER)           # плейсхолдер пішов першим
    assert tg.edits[-1] == (5, 10, "Привіт")         # фінал без курсора
    assert tools.process_calls == 0                  # фолбек не знадобився


def test_status_shown_before_answer():
    tg = FakeTG()
    tools = FakeTools(
        [
            {"status": "🧮 рахую…"},
            {"delta": "Відповідь: 4"},
            {"done": True, "text": "Відповідь: 4", "mode": "agent", "iters": 2},
        ]
    )
    out = _run(stream_reply(tg, tools, 5, {"user_id": 1, "text": "2+2"}))
    assert out == "Відповідь: 4"
    assert any("рахую" in e[2] for e in tg.edits)     # мітку інструмента показали


def test_falls_back_to_classic_when_stream_empty():
    tg = FakeTG()
    tools = FakeTools([], classic="ВІДПОВІДЬ")          # стрім нічого не дав
    out = _run(stream_reply(tg, tools, 5, {"user_id": 1, "text": "x"}))
    assert out == "ВІДПОВІДЬ"
    assert tools.process_calls == 1                     # класичний фолбек
    assert tg.edits[-1] == (5, 10, "ВІДПОВІДЬ")         # плейсхолдер став відповіддю


def test_no_placeholder_returns_empty():
    tg = FakeTG(mid=None)                               # sendMessage не вдався
    tools = FakeTools([{"done": True, "text": "x", "mode": "chat", "iters": 0}])
    out = _run(stream_reply(tg, tools, 5, {"user_id": 1, "text": "x"}))
    assert out == ""                                   # хай роутер шле класично
    assert tg.edits == []


def test_long_answer_overflow_to_extra_messages():
    long = "y" * 5000                                  # > 4096 → перше вікно + хвіст
    tg = FakeTG()
    tools = FakeTools([{"done": True, "text": long, "mode": "chat", "iters": 0}])
    out = _run(stream_reply(tg, tools, 5, {"user_id": 1, "text": "x"}))
    assert out == long
    assert len(tg.edits[-1][2]) <= 4096                # перше вікно в межах ліміту
    assert any(len(t) <= 4096 and t == "y" * (5000 - 4096) for _, t in tg.sent[1:])