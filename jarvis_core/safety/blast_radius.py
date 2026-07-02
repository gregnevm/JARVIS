"""Blast-radius guard — які шляхи автономний луп (kaizen) може правити без людини.

Реалізує `safety_guard`-порт kaizen (інша вісь ризику, ніж CI-гейт: гейт ловить
*зламане*, blast-radius ловить *небажане-але-зелене* — коміт у `.env`/CI-конфіг/інфру
або у файл, який користувач саме редагує). AGENTS.md §5 (S4 human-in-the-loop для
незворотних дій), за зразком `HOSTAGENT_FS_ROOTS` (path-allowlist у hostagent).

**FAIL-CLOSED:** без явного allowlist усе заборонено (інвертує fail-open дефолт). `deny`
завжди перемагає `allow`. Глоби постачає профіль (kaizen `profiles/jarvis` — SSOT), тут
лише чиста, framework-нейтральна логіка зіставлення (імпортовна будь-де, включно з Edge).

Глоб-семантика: `*` зіставляє через `/` (як fnmatch); `**` нормалізується в `*`.
Провідний `**/`-сегмент (gitignore-семантика) зіставляє НУЛЬ-або-більше провідних
сегментів — тож `**/migrations/**` ловить і кореневий `migrations/...`, не лише вкладений
(інакше deny-listed тека в корені репо мовчки проходила б, порушуючи deny-завжди-перемагає).
Для `deny` додатково зіставляється basename — щоб `.env*` ловив і `config/.env` (захист
секретів за будь-якої глибини). Абсолютні/поза-репо шляхи провалюються у fail-closed deny.
"""
from __future__ import annotations

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase


def _normalize(path: str) -> str:
    """Repo-relative, forward-slash, без `./`-префіксів та провідних `/`."""
    norm = path.replace("\\", "/").strip()
    while norm.startswith("./"):
        norm = norm[2:]
    return norm.lstrip("/")


def _matches(path: str, pattern: str) -> bool:
    pat = pattern.replace("\\", "/")
    # Провідний `**/` — globstar-сегмент: зіставляє нуль-або-більше провідних сегментів
    # (gitignore-семантика). Без цього `*/migrations/*` вимагав непорожнього батьк-сегмента
    # і пропускав кореневий `migrations/...`. Решта `**` → `*` (уже зіставляє через `/`).
    if pat.startswith("**/"):
        rest = pat[3:].replace("**", "*")
        return fnmatchcase(path, rest) or fnmatchcase(path, "*/" + rest)
    return fnmatchcase(path, pat.replace("**", "*"))


def _deny_matches(path: str, pattern: str) -> bool:
    if _matches(path, pattern):
        return True
    base = posixpath.basename(path)
    return base != path and _matches(base, pattern)


def decide(path: str, *, allow: Iterable[str], deny: Iterable[str]) -> tuple[bool, str]:
    """`(allowed, reason)` — reason придатний для human-gate-повідомлення."""
    norm = _normalize(path)
    if not norm:
        return False, "empty/invalid path (fail-closed)"
    for pattern in deny:
        if _deny_matches(norm, pattern):
            return False, f"deny:{pattern}"
    allow_list = tuple(allow)
    if not allow_list:
        return False, "no allowlist configured (fail-closed)"
    for pattern in allow_list:
        if _matches(norm, pattern):
            return True, f"allow:{pattern}"
    return False, "outside allowlist (fail-closed)"


def path_allowed(path: str, *, allow: Iterable[str], deny: Iterable[str]) -> bool:
    """True лише якщо `path` у `allow` і не в `deny`. FAIL-CLOSED, deny перемагає."""
    allowed, _ = decide(path, allow=allow, deny=deny)
    return allowed


@dataclass(frozen=True)
class BlastRadius:
    """Незмінна пара allow/deny-глобів. Глоби з профілю (SSOT), не хардкодяться тут."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @classmethod
    def from_globs(cls, allow: Iterable[str] = (), deny: Iterable[str] = ()) -> BlastRadius:
        return cls(tuple(allow), tuple(deny))

    def allows(self, path: str) -> bool:
        return path_allowed(path, allow=self.allow, deny=self.deny)

    def decide(self, path: str) -> tuple[bool, str]:
        return decide(path, allow=self.allow, deny=self.deny)

    def partition(self, paths: Iterable[str]) -> tuple[list[str], list[str]]:
        """`(allowed, blocked)` — для пакетного human-gate по дифу ітерації."""
        allowed: list[str] = []
        blocked: list[str] = []
        for path in paths:
            (allowed if self.allows(path) else blocked).append(path)
        return allowed, blocked
