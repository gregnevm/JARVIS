"""Circuit breaker OllamaClient — перевіряємо логіку розмикання без мережі."""
import time

import pytest

from app.ollama import CircuitOpen, OllamaClient


def test_trip_opens_after_threshold():
    c = OllamaClient("http://x", fail_threshold=3, cooldown=30)
    c._trip()
    c._trip()
    assert c._open_until == 0.0  # ще закрито (2 < 3)
    c._trip()
    assert c._open_until > time.monotonic()  # розімкнуто на 3-й помилці
    assert c._fails == 0  # лічильник скинуто після розмикання


def test_threshold_floored_to_one():
    c = OllamaClient("http://x", fail_threshold=0)  # max(1, 0) == 1
    c._trip()
    assert c._open_until > 0  # відкрилось одразу


async def test_chat_fails_fast_when_open():
    c = OllamaClient("http://x")
    c._open_until = time.monotonic() + 100  # імітуємо розімкнутий брейкер
    with pytest.raises(CircuitOpen):
        await c.chat("model", [{"role": "user", "content": "hi"}])
