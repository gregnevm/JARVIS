"""COMPUTER_PROFILE presets (AM-0.3)."""
import pytest
from app.agent import system_computer
from app.computer_profile import (
    allows_browser,
    allows_screen_click,
    allows_see_screen,
    allows_uia,
    computer_tool_names,
    format_tools_prompt_block,
    normalize_profile,
)
from app.config import settings
from app.toolkit.schemas import agent_tool_schemas


@pytest.fixture()
def computer_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "hostagent_token", "tok")


def test_normalize_profile_invalid():
    assert normalize_profile("bogus") == "safe"


def test_safe_profile_gates_tiers(computer_on: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_profile", "safe")
    monkeypatch.setattr(settings, "enable_browser", True)
    assert not allows_browser()
    assert not allows_uia()
    assert not allows_screen_click()
    names = computer_tool_names()
    assert "run_powershell" in names
    assert "browser_open" not in names
    assert "screen_click" not in names


def test_standard_profile(computer_on: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_profile", "standard")
    monkeypatch.setattr(settings, "enable_browser", True)
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    monkeypatch.setattr(settings, "computer_auto_vision", True)
    assert allows_browser()
    assert allows_uia()
    assert not allows_screen_click()
    assert allows_see_screen()
    assert "see_screen" in computer_tool_names()
    assert "browser_open" in computer_tool_names()


def test_full_profile_includes_screen_click(computer_on: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_profile", "full")
    monkeypatch.setattr(settings, "enable_browser", True)
    assert allows_screen_click()
    names = computer_tool_names()
    assert "screen_click" in names
    assert "screen_type" in names
    assert "screen_hotkey" in names
    assert "screen_scroll" in names


def test_system_computer_lists_available_tools(computer_on: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_profile", "standard")
    monkeypatch.setattr(settings, "enable_browser", True)
    monkeypatch.setattr(settings, "ollama_model_vision", "llava:7b")
    prompt = system_computer()
    assert "browser_open" in prompt
    assert "НЕ доступні" not in prompt
    assert "run_powershell" in prompt


def test_agent_schemas_match_profile(computer_on: None, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_profile", "safe")
    monkeypatch.setattr(settings, "enable_browser", True)
    names = {s["function"]["name"] for s in agent_tool_schemas(computer=True)}
    assert "run_powershell" in names
    assert "browser_open" not in names
    assert "see_screen" not in names


def test_format_tools_prompt_block(computer_on: None):
    block = format_tools_prompt_block()
    assert "T0:" in block
    assert "run_powershell" in block
