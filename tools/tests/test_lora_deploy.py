"""LoRA deploy: path resolve, modelfile, ollama create (mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from app import lora_deploy


def test_resolve_lora_path_relative(tmp_path: Path):
    lora_dir = tmp_path / "twin" / "lora" / "v1"
    lora_dir.mkdir(parents=True)
    (lora_dir / "adapter.gguf").write_bytes(b"x")
    p = lora_deploy.resolve_lora_path("v1", tmp_path)
    assert p == lora_dir.resolve()


def test_build_modelfile():
    mf = lora_deploy.build_modelfile("qwen2.5:7b", Path("/data/active/lora.gguf"))
    assert "FROM qwen2.5:7b" in mf
    assert "ADAPTER /data/active/lora.gguf" in mf


@pytest.mark.asyncio
async def test_deploy_lora_mock_ollama(tmp_path: Path):
    src = tmp_path / "twin" / "lora" / "v1"
    src.mkdir(parents=True)
    gguf = src / "lora.gguf"
    gguf.write_bytes(b"gguf")

    async def _fake_create(*args, **kwargs):
        return {"ok": True, "model": "jarvis-lora:v1", "response": {}}

    with patch.object(lora_deploy, "ollama_create", side_effect=_fake_create):
        with patch.object(lora_deploy, "link_active", return_value=gguf):
            out = await lora_deploy.deploy_lora(
                version="v1",
                path="v1",
                data_dir=tmp_path,
                ollama_host="http://127.0.0.1:11434",
                base_model="qwen2.5:7b",
                model_prefix="jarvis-lora",
                active_dir=tmp_path / "twin" / "lora" / "active",
            )
    assert out["ok"] is True
    assert out["model"] == "jarvis-lora:v1"


@pytest.mark.asyncio
async def test_sync_from_twin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    async def _fetch(_url, client=None):
        return {"ok": True, "version": "v2", "path": "v2"}

    async def _deploy(**kwargs):
        return {"ok": True, "version": "v2", "model": "jarvis-lora:v2"}

    monkeypatch.setattr(lora_deploy, "fetch_active_from_twin", _fetch)
    monkeypatch.setattr(lora_deploy, "deploy_lora", _deploy)
    out = await lora_deploy.sync_active_from_twin(
        "http://twin",
        data_dir=tmp_path,
        ollama_host="http://o",
        base_model="base",
        model_prefix="jarvis-lora",
        active_dir=tmp_path / "active",
    )
    assert out["model"] == "jarvis-lora:v2"


@pytest.mark.asyncio
async def test_ollama_create_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await lora_deploy.ollama_create("http://o", "jarvis-lora:v1", "FROM x", client=client)
    await client.aclose()
    assert out["ok"] is True
