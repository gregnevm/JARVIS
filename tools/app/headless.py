"""Headless apply policy gate (CA-6.4 / AM-4).

`jarvis code fix --no-confirm` має застосовувати правки БЕЗ інтерактивного confirm
(для CI). Це небезпечно, тож дозволено ЛИШЕ за явною політикою
`CODING_HEADLESS_APPLY=true`. Коли дозволено — видаємо короткий session-trust на
прогін (fix-петля dispatch'ить code_edit, який у trust-вікні застосовується без ✅).
Інакше — повертаємо причину відмови (нічого не застосовуємо).
"""
from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger("jarvis.tools.headless")

_DENIED = (
    "Headless auto-apply заборонено політикою (CODING_HEADLESS_APPLY=false). "
    "Запусти без --no-confirm (правки під confirm) або увімкни політику для CI."
)


async def authorize_headless_apply(user_id: int, no_confirm: bool) -> str | None:
    """Авторизує headless apply. None = дозволено (або не headless); рядок = відмова.

    Side-effect: за дозволу видає короткий session-trust для user_id, щоб fix-петля
    застосовувала code_edit без інтерактивного confirm.
    """
    if not no_confirm:
        return None  # інтерактивний режим — confirm діє як завжди
    # Глобальний bypass відкриває headless apply нарівні з явною policy CODING_HEADLESS_APPLY.
    if not (settings.coding_headless_apply or settings.bypass_confirmations):
        return _DENIED
    if int(user_id) <= 0:
        return "Headless apply потребує валідний user_id."
    from .computer_trust import grant_trust

    await grant_trust(user_id, ttl=max(60, int(settings.coding_headless_trust_ttl)))
    logger.info("headless apply authorized for user %s (policy gate open)", user_id)
    return None
