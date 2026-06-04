"""C6.1 vision on-demand VRAM helpers."""
import pytest

from app.config import settings
from app.ollama_vram import vision_chat_payload, vision_vram_scope


@pytest.mark.asyncio
async def test_vision_scope_noop_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ollama_vision_on_demand", False)
    async with vision_vram_scope():
        pass


@pytest.mark.asyncio
async def test_unload_called_when_on_demand(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ollama_vision_on_demand", True)
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    monkeypatch.setattr(settings, "ollama_model_chat", "chat")
    monkeypatch.setattr(settings, "ollama_model_agent", "agent")
    calls: list[str] = []

    async def fake_delete(name: str) -> bool:
        calls.append(name)
        return True

    monkeypatch.setattr("app.ollama_vram._delete_model", fake_delete)
    async with vision_vram_scope():
        pass
    assert calls == ["chat", "agent", "chat", "agent"]


def test_vision_payload_keep_alive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ollama_vision_on_demand", True)
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    p = vision_chat_payload("q", "b64")
    assert p["keep_alive"] == 0
    assert p["model"] == "llava:7b"
