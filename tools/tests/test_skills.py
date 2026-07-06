"""P7 skills loader."""
from pathlib import Path

import pytest
from app import skills


def test_list_skills_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(skills.settings, "data_dir", str(tmp_path))
    assert skills.list_skills() == []


def test_get_skill_from_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(skills.settings, "data_dir", str(tmp_path))
    root = tmp_path / "skills" / "demo"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: Demo\ndescription: test\n---\n\nDo demo things.", encoding="utf-8")
    rec = skills.get_skill("demo")
    assert rec is not None
    assert rec["name"] == "Demo"
    block = skills.skill_prompt_block(rec)
    assert "Demo" in block


async def test_active_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeRedis:
        def __init__(self):
            self.kv = {}

        async def get(self, k):
            return self.kv.get(k)

        async def set(self, k, v):
            self.kv[k] = v

        async def delete(self, k):
            self.kv.pop(k, None)

    fake = FakeRedis()
    monkeypatch.setattr(skills, "get_redis", lambda: fake)
    monkeypatch.setattr(skills.settings, "data_dir", str(tmp_path))
    await skills.set_active_skill(1, "demo")
    assert await skills.active_skill_id(1) == "demo"
