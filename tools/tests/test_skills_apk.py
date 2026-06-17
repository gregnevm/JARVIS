"""Skills: парсинг тегів + прапор `apk` (скіли, що задіюють функції телефона)."""
from __future__ import annotations

import pytest

from app import skills
from app.config import settings


def _write(root, sid, frontmatter):
    d = root / "skills" / sid
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(frontmatter + "\n\nBody.", encoding="utf-8")


@pytest.fixture
def skills_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def test_apk_skill_flagged(skills_dir):
    _write(skills_dir, "phone-digest",
           "---\nname: phone-digest\ndescription: d\ntags: apk, daily\n---")
    items = {s["id"]: s for s in skills.list_skills()}
    assert items["phone-digest"]["apk"] is True
    assert "apk" in items["phone-digest"]["tags"]
    assert "daily" in items["phone-digest"]["tags"]


def test_non_apk_skill_not_flagged(skills_dir):
    _write(skills_dir, "writer", "---\nname: writer\ndescription: d\ntags: writing\n---")
    items = {s["id"]: s for s in skills.list_skills()}
    assert items["writer"]["apk"] is False


def test_requires_field_alias(skills_dir):
    _write(skills_dir, "cam", "---\nname: cam\nrequires: apk\n---")
    items = {s["id"]: s for s in skills.list_skills()}
    assert items["cam"]["apk"] is True
