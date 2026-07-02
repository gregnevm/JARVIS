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


@pytest.mark.parametrize("path", [
    "migrations/001_init.py",          # кореневий (depth-0) — раніше мовчки проходив
    "memory/migrations/001_init.py",   # вкладений
    "a/b/migrations/c/d.sql",          # глибоко вкладений
])
def test_deny_dir_glob_matches_repo_root_and_nested(br: BlastRadius, path: str) -> None:
    # `**/migrations/**` — globstar-префікс зіставляє НУЛЬ-або-більше провідних сегментів,
    # тож кореневий `migrations/...` так само deny, як і вкладений (інакше пробій deny-wins).
    # Пін через reason: голий `allows is False` маскується allowlist-промахом (migrations
    # поза ALLOW), тож асертимо саме deny-хіт — інакше тест зелений і на старому коді.
    assert br.decide(path) == (False, "deny:**/migrations/**")


@pytest.mark.parametrize("path", [
    "__pycache__/x.pyc",               # кореневий (depth-0)
    "tools/__pycache__/x.pyc",         # вкладений
])
def test_leading_globstar_zero_or_more_segments(path: str) -> None:
    # Та сама depth-0-семантика для будь-якого `**/X/**` deny-патерна (напр. tripwire-кеш).
    assert path_allowed(path, allow=("**",), deny=("**/__pycache__/**",)) is False
    # Контроль: не-deny-шлях лишається дозволеним під тим самим широким allow.
    assert path_allowed("tools/app/agent.py", allow=("**",), deny=("**/__pycache__/**",)) is True


def test_leading_globstar_file_shaped_deny_at_root() -> None:
    """`**/x` БЕЗ хвостового `/**` — друга форма пробою: basename-фолбек пропускає
    кореневий файл (base == path), тож рятує саме globstar-гілка `_matches`."""
    assert path_allowed("secrets.txt", allow=("**",), deny=("**/secrets.txt",)) is False
    assert path_allowed("a/b/secrets.txt", allow=("**",), deny=("**/secrets.txt",)) is False


def test_leading_globstar_in_allow_matches_root() -> None:
    """Globstar-семантика діє і на ALLOW-боці (движок profile-pluggable): провідний
    `**/` в allow-глобі впускає depth-0 шлях. Пін проти deny-only-рефактора."""
    assert path_allowed("tests/x.py", allow=("**/tests/**",), deny=()) is True


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
