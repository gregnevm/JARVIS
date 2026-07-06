"""WOL endpoint input validation — fail-fast guard against PowerShell injection.

The mac/broadcast fields are interpolated into single-quoted PowerShell literals, so a
stray "'" would break out and inject commands on the host. Validation runs BEFORE
_run_powershell, so the rejection paths need neither Windows nor a real PS process.
"""
import pytest
from fastapi.testclient import TestClient

from app import main as hostagent_main
from app.config import settings
from app.main import app

TOKEN = {"X-Hostagent-Token": "secret"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "token", "secret")
    return TestClient(app)


def test_wol_requires_token(client: TestClient):
    assert client.post("/wol", json={"mac": "AA:BB:CC:DD:EE:FF"}).status_code == 403


@pytest.mark.parametrize(
    "mac",
    [
        "AA:BB:CC:DD:EE:F'; Start-Process calc; ('",  # single-quote breakout, 6 groups
        "ZZ:BB:CC:DD:EE:FF",  # non-hex octet
        "AA:BB:CC:DD:EE",  # too few groups
        "AA:BB:CC:DD:EE:FF:11",  # too many groups
        "AABBCCDDEEFF",  # no separators
    ],
)
def test_wol_rejects_bad_mac_before_powershell(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mac: str
):
    # if validation leaked, _run_powershell would be reached — make that a hard failure
    monkeypatch.setattr(
        hostagent_main, "_run_powershell", lambda *a, **k: pytest.fail("PS reached on bad mac")
    )
    r = client.post("/wol", json={"mac": mac}, headers=TOKEN)
    assert r.status_code == 400 and r.json()["detail"] == "invalid mac"


@pytest.mark.parametrize(
    "broadcast",
    [
        "255.255.255.255'); Start-Process calc; ('",  # single-quote breakout
        "not-an-ip",
        "255.255.255",  # incomplete
        "999.1.1.1",  # octet out of range
        "192.168.0.1 8.8.8.8",  # embedded space
    ],
)
def test_wol_rejects_bad_broadcast_before_powershell(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, broadcast: str
):
    monkeypatch.setattr(
        hostagent_main, "_run_powershell", lambda *a, **k: pytest.fail("PS reached on bad broadcast")
    )
    r = client.post(
        "/wol", json={"mac": "AA:BB:CC:DD:EE:FF", "broadcast": broadcast}, headers=TOKEN
    )
    assert r.status_code == 400 and r.json()["detail"] == "invalid broadcast"


def test_wol_accepts_valid_mac_and_broadcast(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Legit WOL still works; the built PS carries the normalized, injection-free values."""
    captured: dict[str, str] = {}

    def fake_ps(script: str, *a, **k):
        captured["script"] = script
        return {"code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(hostagent_main, "_run_powershell", fake_ps)
    r = client.post(
        "/wol",
        json={"mac": "aa-bb-cc-dd-ee-ff", "broadcast": "192.168.1.255"},
        headers=TOKEN,
    )
    assert r.status_code == 200
    assert r.json()["mac"] == "AA:BB:CC:DD:EE:FF"  # normalized
    # no stray quote / injected statement escaped into the script
    assert "$mac = 'AA:BB:CC:DD:EE:FF'" in captured["script"]
    assert "$udp.Connect('192.168.1.255', 9)" in captured["script"]
