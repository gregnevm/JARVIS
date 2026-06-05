"""User profile JSON storage."""
from app.user_profile import load_profile, profile_prompt_block, save_profile


def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.user_profile.settings.data_dir", str(tmp_path))
    save_profile(42, {"language": "українська", "style": "коротко"})
    assert "українська" in profile_prompt_block(42)
    p = load_profile(42)
    assert p["language"] == "українська"
