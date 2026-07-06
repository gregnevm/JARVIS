"""Bot /apk command + apk_artifact resolver (Стовп C, CL-3)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from app import apk_artifact
from app.bot import apk as apk_bot
from app.bot.commands import handle_command, is_command


def _write_apk(tmp_path: Path, content: bytes = b"PK\x03\x04fake-apk", meta: dict | None = None) -> Path:
    p = tmp_path / "jarvis-mvp.apk"
    p.write_bytes(content)
    if meta is not None:
        p.with_suffix(p.suffix + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_is_command_recognizes_apk():
    assert is_command("/apk") is True
    assert is_command("/apk@JarvisBot") is True


def test_apk_path_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", "")
    monkeypatch.setattr(apk_artifact.settings, "data_dir", "/data")
    assert apk_artifact.apk_path() == Path("/data") / apk_artifact.DEFAULT_REL


def test_apk_path_explicit_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", "/custom/x.apk")
    assert apk_artifact.apk_path() == Path("/custom/x.apk")


def test_apk_info_none_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(tmp_path / "nope.apk"))
    assert apk_artifact.apk_info() is None
    assert apk_artifact.read_apk_bytes() is None


def test_apk_info_reads_sidecar_meta(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = _write_apk(tmp_path, meta={"version": "9.9.9", "built_at": "2026-06-16T10:00:00Z"})
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(p))
    info = apk_artifact.apk_info()
    assert info is not None
    assert info.version == "9.9.9"
    assert info.built_at == "2026-06-16T10:00:00Z"
    assert info.filename == "jarvis-mvp-9.9.9.apk"
    assert info.size == p.stat().st_size
    assert len(info.sha256) == 64


def test_apk_info_falls_back_to_settings_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = _write_apk(tmp_path)  # no sidecar
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(p))
    monkeypatch.setattr(apk_artifact.settings, "apk_version", "1.2.3")
    info = apk_artifact.apk_info()
    assert info is not None
    assert info.version == "1.2.3"
    assert info.filename == "jarvis-mvp-1.2.3.apk"


@pytest.mark.asyncio
async def test_apk_command_sends_document_when_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = _write_apk(tmp_path, content=b"PK\x03\x04" + b"x" * 100, meta={"version": "0.1.0"})
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(p))
    tg = MagicMock()
    tg.send_message = AsyncMock()
    tg.send_document = AsyncMock(return_value=True)
    ok = await handle_command("/apk", 5, 5, tg, MagicMock(), None, None)
    assert ok is True
    tg.send_document.assert_called_once()
    args, kwargs = tg.send_document.call_args
    assert args[0] == 5  # chat_id
    assert isinstance(args[1], (bytes, bytearray))  # raw apk bytes
    assert kwargs["filename"] == "jarvis-mvp-0.1.0.apk"
    tg.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_apk_command_explains_when_not_built(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(tmp_path / "missing.apk"))
    tg = MagicMock()
    tg.send_message = AsyncMock()
    tg.send_document = AsyncMock()
    ok = await handle_command("/apk", 5, 5, tg, MagicMock(), None, None)
    assert ok is True
    tg.send_document.assert_not_called()
    tg.send_message.assert_called_once()
    assert "ще не зібрано" in tg.send_message.call_args[0][1]


@pytest.mark.asyncio
async def test_notify_admins_sends_to_each(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = _write_apk(tmp_path, meta={"version": "0.1.0"})
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(p))
    tg = MagicMock()
    tg.send_message = AsyncMock()
    tg.send_document = AsyncMock(return_value=True)
    delivered = await apk_bot.notify_admins_apk_ready(tg, [11, 22])
    assert delivered == 2
    assert tg.send_document.call_count == 2


@pytest.mark.asyncio
async def test_notify_admins_noop_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(apk_artifact.settings, "apk_artifact_path", str(tmp_path / "missing.apk"))
    tg = MagicMock()
    tg.send_message = AsyncMock()
    tg.send_document = AsyncMock()
    delivered = await apk_bot.notify_admins_apk_ready(tg, [11, 22])
    assert delivered == 0
    tg.send_document.assert_not_called()
