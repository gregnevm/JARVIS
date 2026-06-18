"""Тести blast-radius guard (kaizen safety_guard-порт). Без мережі/БД, чисті."""
from __future__ import annotations

import pytest

from jarvis_core.safety import BlastRadius, path_allowed
from jarvis_core.safety.blast_radius import decide

# Глоби JARVIS-профілю (kaizen profiles/jarvis/profile.md §7) — джерело правди там.
ALLOW = (
    "tools/**", "jarvis_core/**", "memory/**", "gateway/**",
    "hostagent/**", "twin/**", "docs/**", ".claude/skills/**",
)
DENY = (".env*", ".github/workflows/**", "docker-compose.yml", "**/migrations/**", "mobile/**", "db/**")


@pytest.fixture
def br() -> BlastRadius:
    return BlastRadius.from_globs(ALLOW, DENY)


@pytest.mark.parametrize("path", [
    "tools/app/agent.py",
    "jarvis_core/safety/blast_radius.py",
    "memory/app/db.py",
    "docs/CODING_AGENT_ROADMAP.md",
    ".claude/skills/kaizen/SKILL.md",
])
def test_allowed_paths(br: BlastRadius, path: str) -> None:
    assert br.allows(path) is True


@pytest.mark.parametrize("path", [
    ".env", ".env.example", ".env.bak.20260612-corrupt",  # секрети
    ".github/workflows/ci.yml",                            # CI-конфіг
    "docker-compose.yml",                                  # інфра
    "memory/migrations/001_init.py",                       # незворотна міграція
    "mobile/app/build.gradle",
    "db/init.sql",
])
def test_denied_paths(br: BlastRadius, path: str) -> None:
    assert br.allows(path) is False


def test_deny_matches_basename_at_any_depth(br: BlastRadius) -> None:
    # `.env*` має ловити секрет навіть у вкладеній теці (захист за будь-якої глибини).
    assert br.allows("gateway/config/.env") is False


def test_deny_wins_over_allow() -> None:
    # навіть найширший allowlist не перебиває deny.
    allowed, blocked = BlastRadius.from_globs(("**",), (".env*",)).partition(
        ["tools/x.py", ".env", "anything/else.py"]
    )
    assert ".env" in blocked
    assert "tools/x.py" in allowed and "anything/else.py" in allowed


def test_fail_closed_without_allowlist() -> None:
    # без allowlist — усе заборонено (інверсія fail-open).
    assert path_allowed("tools/app/agent.py", allow=(), deny=()) is False


def test_outside_allowlist_denied(br: BlastRadius) -> None:
    assert br.allows("scripts/deploy.sh") is False   # scripts/ не в allow
    assert br.allows("README.md") is False           # корінь не в allow


def test_absolute_and_outside_repo_denied(br: BlastRadius) -> None:
    assert br.allows("/etc/passwd") is False
    assert br.allows("O:/JARVIS/.env") is False       # basename .env → deny


@pytest.mark.parametrize("path", [
    "tools\\app\\agent.py",   # Windows backslash
    "./tools/app/agent.py",   # leading ./
    "tools/app/agent.py",
])
def test_path_normalization(br: BlastRadius, path: str) -> None:
    assert br.allows(path) is True


def test_empty_path_denied(br: BlastRadius) -> None:
    assert br.allows("") is False
    assert br.allows("   ") is False


def test_decide_reason_strings(br: BlastRadius) -> None:
    assert decide(".env", allow=ALLOW, deny=DENY) == (False, "deny:.env*")
    ok, reason = br.decide("tools/app/agent.py")
    assert ok is True and reason.startswith("allow:")
    assert br.decide("scripts/x.sh") == (False, "outside allowlist (fail-closed)")
    assert decide("tools/x.py", allow=(), deny=())[1] == "no allowlist configured (fail-closed)"


def test_partition_splits_diff(br: BlastRadius) -> None:
    diff = ["tools/app/a.py", ".env", "jarvis_core/x.py", ".github/workflows/ci.yml"]
    allowed, blocked = br.partition(diff)
    assert allowed == ["tools/app/a.py", "jarvis_core/x.py"]
    assert blocked == [".env", ".github/workflows/ci.yml"]
