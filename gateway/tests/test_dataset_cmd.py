"""Bot /dataset command."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.bot.commands import handle_command


@pytest.mark.asyncio
async def test_dataset_admin_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.bot.commands.is_admin", lambda uid: uid == 99)
    tg = MagicMock()
    tg.send_message = AsyncMock()
    ok = await handle_command("/dataset", 1, 1, tg, MagicMock(), None, None)
    assert ok is True
    tg.send_message.assert_called_once()
    assert "адмін" in tg.send_message.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_dataset_export_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.bot.commands.is_admin", lambda uid: True)
    tools = MagicMock()
    tools.dataset_stats = AsyncMock(return_value={"curated_turns": 3, "files": 1})
    tools.export_dataset = AsyncMock(
        return_value={"train": 2, "holdout": 1, "train_path": "/data/x.jsonl"}
    )
    tg = MagicMock()
    tg.send_message = AsyncMock()
    ok = await handle_command("/dataset", 1, 7, tg, MagicMock(), None, tools)
    assert ok is True
    tools.export_dataset.assert_called_once_with(7)
