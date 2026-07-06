"""Єдиний внутрішній RPC-helper JARVIS (R2 «Тонкий шлюз», P7 SSOT).

Проксі-виклики gateway → tools/memory/twin/ollama досі жили у ~20 рукописних
httpx-блоках із різнобоєм таймаутів і формату помилок. Тепер одна точка істини:

    from jarvis_core.service_client import ServiceError, call_dict

    data = await call_dict(settings.memory_url, "POST", "/context/store",
                           json=payload, timeout=15.0, service="memory")

- **error-envelope:** будь-який фейл → `ServiceError` (`status=None` — транспорт/
  таймаут, `status=N` — не-2xx). Викликач сам вирішує — ковтати, конвертувати в
  HTTP 502 чи віддавати заглушку: семантика наявних місць виклику зберігається 1:1.
- **ретраї:** лише транспортні помилки та 502/503/504 (перевантажений/рестартований
  сусід). За замовчуванням вимкнено — вмикається там, де було (напр. dashboard ×3).
- **таймаути:** per-call, дефолт 15s — наявні значення переносяться 1:1.
- Виділені клієнти-адаптери (telegram/whisper/tts/tools_client_base) **не** мігрують:
  довгоживучі з'єднання з доменною логікою (критерій прийняття §1 спеки).

Модуль не експортується з `jarvis_core/__init__.py` (та сама причина, що
`http_helpers`) — імпортуй явно: `from jarvis_core.service_client import call`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.service_client")

DEFAULT_TIMEOUT = 15.0
# Статуси, після яких є сенс повторити: сусідній сервіс перевантажений або рестартує.
RETRYABLE_STATUSES = frozenset({502, 503, 504})


class ServiceError(Exception):
    """Error-envelope внутрішнього RPC.

    `status=None` — сервіс недосяжний/таймаут (транспорт); `status=N` — HTTP N.
    Повідомлення безпечне для логів: без тіла запиту (там можуть бути секрети),
    detail — короткий зріз відповіді сервера або текст транспортної помилки.
    """

    def __init__(
        self,
        service: str,
        method: str,
        path: str,
        *,
        status: int | None = None,
        detail: str = "",
    ) -> None:
        self.service = service
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail
        where = f"{service or 'service'} {method} {path}"
        what = f"HTTP {status}" if status is not None else "unreachable"
        suffix = f" — {detail}" if detail else ""
        super().__init__(f"{where}: {what}{suffix}")


def _safe_detail(resp: httpx.Response, limit: int = 200) -> str:
    """Короткий зріз помилки сервера: JSON `detail`, якщо є, інакше — тіло."""
    try:
        body = resp.json()
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            return body["detail"][:limit]
    except ValueError:
        pass
    return resp.text[:limit]


async def call(
    base_url: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 0,
    retry_backoff: float = 0.2,
    service: str = "",
    client: httpx.AsyncClient | None = None,
) -> Any:
    """HTTP-виклик внутрішнього сервісу → розпарсений JSON. Кидає `ServiceError`.

    `client` — опційний довгоживучий `httpx.AsyncClient` (реюз з'єднань, DI у
    тестах через MockTransport); без нього створюється одноразовий — семантика
    теперішніх `async with httpx.AsyncClient(...)`-блоків 1:1.
    """
    url = f"{base_url.rstrip('/')}{path}"
    verb = method.upper()
    attempt = 0
    while True:
        try:
            if client is None:
                async with httpx.AsyncClient(timeout=timeout) as cli:
                    resp = await cli.request(
                        verb, url, json=json, params=params, headers=headers
                    )
            else:
                resp = await client.request(
                    verb, url, json=json, params=params, headers=headers, timeout=timeout
                )
        except httpx.HTTPError as exc:
            if attempt < retries:
                attempt += 1
                await asyncio.sleep(retry_backoff * attempt)
                continue
            raise ServiceError(service, verb, path, detail=str(exc)) from exc

        if resp.status_code in RETRYABLE_STATUSES and attempt < retries:
            attempt += 1
            await asyncio.sleep(retry_backoff * attempt)
            continue
        if resp.status_code >= 400:
            raise ServiceError(
                service, verb, path, status=resp.status_code, detail=_safe_detail(resp)
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ServiceError(
                service, verb, path, status=resp.status_code, detail="invalid JSON body"
            ) from exc


async def call_dict(
    base_url: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 0,
    retry_backoff: float = 0.2,
    service: str = "",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Як `call`, але гарантує dict (не-dict JSON → `{}`) — найчастіший патерн
    місць виклику: `out if isinstance(out, dict) else {}`."""
    out = await call(
        base_url,
        method,
        path,
        json=json,
        params=params,
        headers=headers,
        timeout=timeout,
        retries=retries,
        retry_backoff=retry_backoff,
        service=service,
        client=client,
    )
    return out if isinstance(out, dict) else {}
