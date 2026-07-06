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

    async def fake_unload(name: str) -> bool:
        calls.append(name)
        return True

    monkeypatch.setattr("app.ollama_vram._unload_model", fake_unload)
    async with vision_vram_scope():
        pass
    assert calls == ["chat", "agent", "chat", "agent"]


@pytest.mark.asyncio
async def test_unload_uses_generate_keep_alive_not_delete(monkeypatch: pytest.MonkeyPatch):
    """Регресія: вивантаження = /api/generate keep_alive=0, НЕ деструктивний /api/delete."""
    monkeypatch.setattr(settings, "ollama_host", "http://ollama:11434")

    async def fake_loaded() -> set[str]:
        return {"agent"}

    monkeypatch.setattr("app.ollama_vram._loaded_models", fake_loaded)
    seen: dict[str, object] = {}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None):
            seen["url"] = url
            seen["json"] = json
            return FakeResp()

    monkeypatch.setattr("app.ollama_vram.httpx.AsyncClient", FakeClient)

    from app.ollama_vram import _unload_model

    ok = await _unload_model("agent")
    assert ok is True
    assert str(seen["url"]).endswith("/api/generate")
    assert "delete" not in str(seen["url"])
    assert seen["json"] == {"model": "agent", "keep_alive": 0}


@pytest.mark.asyncio
async def test_unload_skips_when_not_loaded(monkeypatch: pytest.MonkeyPatch):
    """Якщо модель не у VRAM — не вантажимо її лише щоб вивантажити (жодного POST)."""
    async def fake_loaded() -> set[str]:
        return set()

    monkeypatch.setattr("app.ollama_vram._loaded_models", fake_loaded)

    def boom(*a, **k):  # будь-який httpx виклик = помилка тесту
        raise AssertionError("must not call ollama when model not loaded")

    monkeypatch.setattr("app.ollama_vram.httpx.AsyncClient", boom)

    from app.ollama_vram import _unload_model

    assert await _unload_model("agent") is True


def test_vision_payload_keep_alive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ollama_vision_on_demand", True)
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    p = vision_chat_payload("q", "b64")
    assert p["keep_alive"] == 0
    assert p["model"] == "llava:7b"
