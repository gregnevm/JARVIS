"""ModelRegistry — register / promote / rollback / get_active (in-memory SQLite)."""
import pytest

from app.registry import ModelRegistry


def test_register_is_candidate():
    r = ModelRegistry()
    rid = r.register_lora("v1", "/lora/v1.gguf", eval_score=0.8)
    assert rid > 0
    versions = r.list_versions()
    assert len(versions) == 1
    assert versions[0]["version"] == "v1"
    assert versions[0]["status"] == "candidate"
    assert r.get_active() is None  # candidate ще не active


def test_promote_sets_active():
    r = ModelRegistry()
    r.register_lora("v1", "/lora/v1.gguf", eval_score=0.8)
    r.promote("v1")
    active = r.get_active()
    assert active is not None
    assert active["version"] == "v1"
    assert active["status"] == "active"


def test_promote_archives_previous():
    r = ModelRegistry()
    r.register_lora("v1", "/lora/v1.gguf")
    r.register_lora("v2", "/lora/v2.gguf")
    r.promote("v1")
    r.promote("v2")
    active = r.get_active()
    assert active is not None and active["version"] == "v2"
    # v1 має стати archived (рівно один active у системі)
    statuses = {v["version"]: v["status"] for v in r.list_versions()}
    assert statuses == {"v1": "archived", "v2": "active"}


def test_rollback_restores_previous():
    r = ModelRegistry()
    r.register_lora("v1", "/lora/v1.gguf")
    r.register_lora("v2", "/lora/v2.gguf")
    r.promote("v1")
    r.promote("v2")          # active=v2, archived=v1
    restored = r.rollback(1)  # повертаємо v1
    assert restored is not None and restored["version"] == "v1"
    active = r.get_active()
    assert active is not None and active["version"] == "v1"
    statuses = {v["version"]: v["status"] for v in r.list_versions()}
    assert statuses == {"v1": "active", "v2": "archived"}


def test_rollback_no_archived_returns_none():
    r = ModelRegistry()
    r.register_lora("v1", "/lora/v1.gguf")
    r.promote("v1")
    assert r.rollback(1) is None  # немає archived → нема куди відкочуватись


def test_promote_unknown_raises():
    r = ModelRegistry()
    with pytest.raises(KeyError):
        r.promote("nonexistent")


def test_duplicate_version_rejected():
    r = ModelRegistry()
    r.register_lora("v1", "/lora/v1.gguf")
    with pytest.raises(Exception):  # sqlite3.IntegrityError (UNIQUE)
        r.register_lora("v1", "/lora/v1b.gguf")
