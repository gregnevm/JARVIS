"""Browser tools (C3) — mock Playwright, без мережі."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import browser
from app.computer_confirm import is_mutating, tier_for
from app.config import settings


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com"
        self.clicks: list[str] = []
        self.fills: list[tuple[str, str]] = []

    async def goto(self, url, **kwargs):
        self.url = url

    async def title(self):
        return "Example"

    async def evaluate(self, script):
        if "innerText" in script:
            return "Hello world"
        return [{"tag": "a", "text": "Link", "sel": "#x"}]

    async def click(self, selector, **kwargs):
        self.clicks.append(selector)

    async def fill(self, selector, value, **kwargs):
        self.fills.append((selector, value))


@pytest.fixture(autouse=True)
def _reset_browser_state():
    browser._page = None
    browser._browser = None
    browser._page_url = ""
    yield
    browser._page = None
    browser._browser = None
    browser._page_url = ""


@pytest.fixture
def browser_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_browser", True)


async def test_browser_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_browser", False)
    assert "вимкнено" in await browser.browser_open("https://x.com")


async def test_browser_bad_url(browser_on):
    assert "Некоректний" in await browser.browser_open("ftp://x.com")
    assert "Некоректний" in await browser.browser_open("")


async def test_browser_open_read(browser_on, monkeypatch: pytest.MonkeyPatch):
    fake = FakePage()

    async def _ensure():
        browser._page = fake
        browser._page_url = ""
        return fake

    monkeypatch.setattr(browser, "_ensure_page", _ensure)
    out = await browser.browser_open("https://example.com")
    assert "Example" in out
    text = await browser.browser_read()
    assert "Hello world" in text
    assert "example.com" in text


async def test_browser_click_fill(browser_on, monkeypatch: pytest.MonkeyPatch):
    fake = FakePage()
    browser._page = fake
    browser._page_url = "https://example.com"
    await browser.browser_click("#btn")
    await browser.browser_fill("#q", "jarvis")
    assert fake.clicks == ["#btn"]
    assert fake.fills == [("#q", "jarvis")]


async def test_browser_eval(browser_on):
    fake = FakePage()
    browser._page = fake
    browser._page_url = "https://example.com"

    async def _eval(script: str):
        if script.strip() == "1+1":
            return 42
        return await FakePage.evaluate(fake, script)

    fake.evaluate = _eval  # type: ignore[method-assign]
    assert await browser.browser_eval("1+1") == "42"


def test_browser_mutating_confirm():
    assert tier_for("browser_open") == "T2"
    assert not is_mutating("browser_open", {"url": "https://a"})
    assert not is_mutating("browser_read", {})
    assert is_mutating("browser_click", {"selector": "#x"})
    assert is_mutating("browser_fill", {"selector": "#x", "value": "y"})
    assert not is_mutating("browser_eval", {"js": "1+1"})


def test_browser_schemas_gated(monkeypatch: pytest.MonkeyPatch):
    from app import toolkit

    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_profile", "standard")
    monkeypatch.setattr(settings, "enable_browser", False)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "browser_open" not in names
    monkeypatch.setattr(settings, "enable_browser", True)
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "browser_eval" in names


async def test_dispatch_browser_eval(browser_on, monkeypatch: pytest.MonkeyPatch):
    from app import toolkit

    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_profile", "standard")
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr("app.browser.browser_eval", AsyncMock(return_value="ok"))
    out = await toolkit.dispatch("browser_eval", {"js": "x"}, user_id=1)
    assert out == "ok"
