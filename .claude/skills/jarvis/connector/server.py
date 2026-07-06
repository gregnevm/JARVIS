"""jarvis-connector — вихідний MCP stdio-сервер (Фаза 1: chat + whoami).

Робить JARVIS **роз'ємом**, який втикається в Claude Code / будь-який MCP-хост:
`claude mcp add jarvis -- python connector/server.py`. Конектор httpx-ить **локальний**
gateway client-API (`/api/v1/*`) — інференс лишається локальним (S1).

Архітектура (Ports & Adapters, концепт §3):
  * Ядро (цей файл) — generic HTTP-міст: порти `endpoint`/`auth`/`identity`/`audit`.
  * Adapter (jarvis) — JARVIS-конкретика винесена в `_ROUTES` + `adapters/jarvis/manifest.json`
    (drift між ними ловить `tests/test_tool_mapping.py::test_manifest_matches_routes`).

Тестованість (P8): ядро (`ConnectorConfig` / `JarvisClient`) не імпортує `mcp` — FastMCP
підвантажується лазі в `build_server()`, тож юніт-тести ганяються без MCP-SDK.

Audit (P9/C1): кожен виклик лишає jsonl-рядок через SSOT `jarvis_core/llm/jsonl_log.py:JsonlLog`
(підвантажений з файлу, без важкого `jarvis_core`-дерева). У слід іде лише **метадані**
(довжини, режим) — НІКОЛИ сирий текст/відповідь (anti-leak, як у gateway).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

# --- ADAPTER BINDING (jarvis) -------------------------------------------------
# JARVIS-специфічні маршрути. Дзеркаляться в adapters/jarvis/manifest.json;
# консистентність — під тестом (test_manifest_matches_routes). Новий tool = новий рядок тут
# + у manifest, без зміни ядра (Open/Closed, P5).
_ROUTES: dict[str, tuple[str, str]] = {
    # P1 — base
    "whoami": ("GET", "/api/v1/whoami"),
    "chat": ("POST", "/api/v1/chat"),
    # P2 — контекст-память (культура P9/P10; gateway-гейт ENABLE_CONTEXT_API)
    "context_search": ("POST", "/api/v1/context/search"),
    "context_recent": ("POST", "/api/v1/context/recent"),
    "context_ingest": ("POST", "/api/v1/ingest/events"),
    # P3 — confirm-gated дії (S4): дія дispatch-иться, апрув — ОКРЕМИМ викликом, ніколи не авто
    "code": ("POST", "/api/v1/code/task"),
    "computer": ("POST", "/api/v1/driver/exec"),
    "confirm_pending": ("GET", "/api/v1/confirm/pending"),
    "confirm_approve": ("POST", "/api/v1/confirm/approve"),
    "confirm_cancel": ("POST", "/api/v1/confirm/cancel"),
    # P4 — керований MCP-хаб (gateway-гейт ENABLE_MCP_HUB): ре-експонує агрегатор downstream-серверів
    "mcp_list": ("GET", "/api/v1/mcp/servers"),
    "mcp_call": ("POST", "/api/v1/mcp/call"),
}
_DEFAULT_BASE_URL = "http://localhost:8000"  # S1: локальний інстанс за дефолтом


class ConnectorConfigError(RuntimeError):
    """Порт не заповнений (endpoint/auth) → конектор відмовляється стартувати (fail-fast)."""


# --- Audit (порт `audit`) -----------------------------------------------------

class _FallbackJsonlLog:
    """Мінімальний append-only sink, якщо SSOT JsonlLog недосяжний (конектор скопійовано окремо)."""

    def __init__(self, path: str | Path) -> None:
        self._p = Path(path)
        self._p.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> int:
        with self._p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return 0


def _resolve_jsonl_log_cls() -> Any:
    """Реюз SSOT `jarvis_core/llm/jsonl_log.py:JsonlLog` БЕЗ імпорту важкого пакета.

    Завантажуємо модуль прямо з файлу (importlib), оминаючи `jarvis_core/__init__`
    (який тягне facade/ollama-адаптери). Не знайшли — тихий фолбек.
    """
    try:
        repo_root = Path(__file__).resolve().parents[4]  # connector→jarvis→skills→.claude→ROOT
        mod_path = repo_root / "jarvis_core" / "llm" / "jsonl_log.py"
        if mod_path.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("_jarvis_connector_jsonl", mod_path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.JsonlLog
    except Exception:  # noqa: BLE001 — audit ніколи не валить конектор
        pass
    return _FallbackJsonlLog


def make_audit(path: str | Path) -> Callable[..., None]:
    """Повертає sink `(tool, summary, tags, status='ok') -> None`. Ніколи не кидає."""
    logger = _resolve_jsonl_log_cls()(path)

    def audit(tool: str, summary: str, tags: list[str], status: str = "ok") -> None:
        try:
            logger.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "tool": tool,
                    "summary": summary,
                    "tags": tags,
                    "status": status,
                }
            )
        except Exception:  # noqa: BLE001 — слід не критичний для виклику
            pass

    return audit


def _default_audit_path() -> Path:
    try:
        return Path(__file__).resolve().parents[4] / "data" / "logs" / "jarvis_connector.jsonl"
    except Exception:  # noqa: BLE001
        return Path("jarvis_connector.jsonl")


def _repo_env_password(env_path: Path | None = None) -> str | None:
    """Пароль із co-located репо-`.env` (PLATFORM_PASSWORD має пріоритет над ADMIN_PANEL_PASSWORD).

    Дозволяє `claude mcp add jarvis -- python server.py` БЕЗ секрета в MCP-конфігу — секрет лишається
    у `.env` (S1). Викликається лише коли creds не задані в оточенні (gating у `from_env`).
    """
    try:
        p = env_path if env_path is not None else (Path(__file__).resolve().parents[4] / ".env")
        if not p.is_file():
            return None
        found: dict[str, str] = {}
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in ("PLATFORM_PASSWORD", "ADMIN_PANEL_PASSWORD"):
                val = v.strip().strip('"').strip("'")
                if val:
                    found[k] = val
        return found.get("PLATFORM_PASSWORD") or found.get("ADMIN_PANEL_PASSWORD")
    except Exception:  # noqa: BLE001 — fallback ніколи не валить старт
        return None


# --- Config (порти `endpoint` + `auth`) ---------------------------------------

@dataclass(frozen=True)
class ConnectorConfig:
    base_url: str
    api_key: str | None
    basic_user: str
    basic_password: str | None
    timeout: float
    audit_path: str
    redact: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ConnectorConfig":
        e: Mapping[str, str] = os.environ if env is None else env
        base_url = (e.get("JARVIS_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        api_key = e.get("JARVIS_API_KEY") or None
        basic_user = e.get("JARVIS_BASIC_USER") or "admin"
        # `sk-jarvis-*` per-org ще не реалізований (AP-1) → робочий self-hosted шлях = Basic/JWT.
        # Gateway приймає PLATFORM_PASSWORD АБО ADMIN_PANEL_PASSWORD (auth.py:active_browser_password).
        basic_password = (
            e.get("JARVIS_BASIC_PASSWORD")
            or e.get("PLATFORM_PASSWORD")
            or e.get("ADMIN_PANEL_PASSWORD")
            or None
        )
        if not base_url:
            raise ConnectorConfigError("endpoint port unfilled: JARVIS_BASE_URL is empty")
        # Fallback на co-located репо-`.env` ЛИШЕ для реального оточення (env is None), не для тестів
        # з явним env-словником — інакше fail-fast став би недетермінованим.
        if env is None and not api_key and not basic_password:
            basic_password = _repo_env_password() or None
        if not api_key and not basic_password:
            raise ConnectorConfigError(
                "auth port unfilled: set JARVIS_API_KEY (Bearer) "
                "or JARVIS_BASIC_PASSWORD / PLATFORM_PASSWORD (Basic), "
                "or run co-located with a repo .env"
            )
        try:
            timeout = float(e.get("JARVIS_TIMEOUT") or "60")
        except ValueError as exc:
            raise ConnectorConfigError("JARVIS_TIMEOUT must be a number") from exc
        audit_path = e.get("JARVIS_CONNECTOR_AUDIT") or str(_default_audit_path())
        # S1: скраб секретів у вихідних результатах ПЕРЕД хост-AI — default ON, opt-out JARVIS_REDACT=0.
        redact = (e.get("JARVIS_REDACT") or "1").strip().lower() not in ("0", "false", "no", "off")
        return cls(base_url, api_key, basic_user, basic_password, timeout, audit_path, redact)

    def httpx_auth(self) -> httpx.Auth | None:
        if self.api_key:
            return None  # Bearer іде заголовком (див. headers())
        if self.basic_password:
            return httpx.BasicAuth(self.basic_user, self.basic_password)
        return None

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}


# --- Client (порт `identity` + виклики tool-ів) -------------------------------

def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _make_redactor() -> Callable[[str], str]:
    """Скрабер КРЕДЕНШЕЛІВ для вихідних результатів (S1). Реюз credential-правил SSOT
    `jarvis_core.passport.redaction`, але БЕЗ `card/iban/otp` — вони матчать легітимні числові ID
    (напр. org_id-UUID `0000-0000-…` → хибне `[REDACTED:card]`). Виключення (не включення) →
    нові credential-правила SSOT підхопляться авто. Fallback — мінімальний набір (якщо без jarvis_core).
    """
    try:
        from jarvis_core.passport.redaction import _DEFAULT_RULES, Redactor

        _DROP = {"card", "iban", "otp"}  # числова PII → false-positive на ID/UUID/числах
        return Redactor([r for r in _DEFAULT_RULES if r.name not in _DROP]).redact
    except Exception:  # noqa: BLE001 — fallback, не валимо конектор
        import re

        _pats = [
            re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}\b"),
            re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
            re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        ]

        def _scrub(text: str) -> str:
            for pat in _pats:
                text = pat.sub("[REDACTED:secret]", text)
            return text

        return _scrub


def _redact_value(value: Any, scrub: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [_redact_value(v, scrub) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v, scrub) for k, v in value.items()}
    return value


class JarvisClient:
    """Тонкий httpx-клієнт до локального gateway client-API. Типовані tool-методи."""

    def __init__(
        self,
        config: ConnectorConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self._cfg = config
        self._audit = audit or make_audit(config.audit_path)
        self._scrub: Callable[[str], str] | None = _make_redactor() if config.redact else None
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            auth=config.httpx_auth(),
            headers=config.headers(),
            transport=transport,
        )

    def __enter__(self) -> "JarvisClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _call(self, tool: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        method, path = _ROUTES[tool]
        resp = self._http.request(method, path, json=json_body)
        resp.raise_for_status()
        data = _as_dict(resp.json())
        # порт `redaction` (S1): скраб секретів ПЕРЕД поверненням у хост-AI (default on).
        if self._scrub is not None:
            data = _as_dict(_redact_value(data, self._scrub))
        return data

    def whoami(self) -> dict[str, Any]:
        data = self._call("whoami")
        self._audit(
            "whoami",
            f"identity org={data.get('org_id')} plan={data.get('plan')} via={data.get('via')}",
            ["kind:connector-call", "tool:whoami", "pillar:A"],
        )
        return data

    def chat(self, text: str, mode: str = "auto") -> dict[str, Any]:
        data = self._call("chat", {"text": text, "mode": mode})
        # ТІЛЬКИ метадані у слід — без сирого тексту/відповіді (anti-leak).
        self._audit(
            "chat",
            f"chat mode={mode} chars_in={len(text)} chars_out={len(str(data.get('reply', '')))}",
            ["kind:connector-call", "tool:chat", "pillar:C"],
        )
        return data

    # --- P2: контекст-память (P9/P10; за ENABLE_CONTEXT_API) ---

    def context_search(self, query: str, top_k: int = 8,
                       tags: list[str] | None = None, since: str | None = None) -> dict[str, Any]:
        data = self._call("context_search",
                          {"query": query, "top_k": top_k, "tags": tags, "since": since})
        self._audit("context_search",
                    f"context_search q_chars={len(query)} top_k={top_k} hits={len(data.get('results') or [])}",
                    ["kind:connector-call", "tool:context_search", "pillar:A"])
        return data

    def context_recent(self, limit: int = 20, kind: str | None = None,
                       tags: list[str] | None = None) -> dict[str, Any]:
        data = self._call("context_recent", {"limit": limit, "kind": kind, "tags": tags})
        self._audit("context_recent",
                    f"context_recent limit={limit} kind={kind} got={len(data.get('events') or [])}",
                    ["kind:connector-call", "tool:context_recent", "pillar:A"])
        return data

    def context_ingest(self, summary: str, kind: str = "note",
                       tags: list[str] | None = None, sensitivity: str = "personal") -> dict[str, Any]:
        # Одно-подієвий batch; повний паспорт (redaction + теги) добудовує gateway `_build_store`.
        event = {"kind": kind, "summary": summary, "tags": tags or [], "sensitivity": sensitivity}
        data = self._call("context_ingest", {"events": [event]})
        self._audit("context_ingest",
                    f"context_ingest kind={kind} accepted={data.get('accepted')} dup={data.get('duplicates')}",
                    ["kind:connector-call", "tool:context_ingest", "pillar:A"])
        return data

    # --- P3: confirm-gated дії (S4) — дispatch ≠ виконання; апрув ОКРЕМО, ніколи не авто ---

    def code(self, text: str, target: str = "local") -> dict[str, Any]:
        data = self._call("code", {"text": text, "target": target})
        self._audit("code", f"code target={target} chars_in={len(text)}",
                    ["kind:connector-call", "tool:code", "pillar:B"])
        return data

    def computer(self, text: str) -> dict[str, Any]:
        data = self._call("computer", {"text": text})
        self._audit("computer", f"computer chars_in={len(text)}",
                    ["kind:connector-call", "tool:computer", "pillar:B"])
        return data

    def confirm_pending(self) -> dict[str, Any]:
        data = self._call("confirm_pending")
        self._audit("confirm_pending", f"confirm_pending pending={data.get('pending')}",
                    ["kind:connector-call", "tool:confirm_pending", "pillar:B"])
        return data

    def confirm_approve(self, code: str) -> dict[str, Any]:
        # Людський апрув мутуючої дії (S4). Конектор НІКОЛИ не кличе це сам.
        data = self._call("confirm_approve", {"code": code})
        self._audit("confirm_approve", f"confirm_approve code_len={len(code)}",
                    ["kind:connector-call", "tool:confirm_approve", "pillar:B"], "human-approved")
        return data

    def confirm_cancel(self) -> dict[str, Any]:
        data = self._call("confirm_cancel")
        self._audit("confirm_cancel", "confirm_cancel",
                    ["kind:connector-call", "tool:confirm_cancel", "pillar:B"])
        return data

    # --- P4: керований MCP-хаб (gateway ENABLE_MCP_HUB; redaction — наступний крок) ---

    def mcp_list(self) -> dict[str, Any]:
        data = self._call("mcp_list")
        self._audit("mcp_list", f"mcp_list servers={len(data.get('servers') or [])}",
                    ["kind:connector-call", "tool:mcp_list", "pillar:A"])
        return data

    def mcp_call(self, server: str, tool: str,
                 arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._call("mcp_call", {"server": server, "tool": tool, "arguments": arguments or {}})
        self._audit("mcp_call", f"mcp_call server={server} tool={tool}",
                    ["kind:connector-call", "tool:mcp_call", "pillar:A"])
        return data


# --- MCP server (порт `capabilities`; FastMCP підвантажується лазі) ------------

def build_server(client: JarvisClient | None = None) -> Any:
    """Будує FastMCP-сервер із tool-ами whoami/chat. `mcp` імпортується тут (lazy).

    mypy-strict припускає присутність задекларованої залежності `mcp` (connector/requirements.txt);
    ядро (ConnectorConfig/JarvisClient) лишається імпортовним і тестовним без неї.
    """
    from mcp.server.fastmcp import FastMCP

    cli = client if client is not None else JarvisClient(ConnectorConfig.from_env())
    server = FastMCP("jarvis")

    def whoami() -> dict[str, Any]:
        """Хто я в JARVIS: org / user / role / plan / limits (локальний інстанс, S1)."""
        return cli.whoami()

    def chat(text: str, mode: str = "auto") -> dict[str, Any]:
        """Спитати JARVIS один хід (локальний інференс). mode: auto|chat|agent|computer."""
        return cli.chat(text, mode)

    def context_search(query: str, top_k: int = 8) -> dict[str, Any]:
        """Семантичний пошук у памʼяті JARVIS (паспорти P9/P10). Потребує ENABLE_CONTEXT_API."""
        return cli.context_search(query, top_k)

    def context_recent(limit: int = 20, kind: str = "") -> dict[str, Any]:
        """Останні події памʼяті (прозорість). kind='' = усі. Потребує ENABLE_CONTEXT_API."""
        return cli.context_recent(limit, kind or None)

    def context_ingest(summary: str, kind: str = "note") -> dict[str, Any]:
        """Покласти паспорт у памʼять JARVIS (summary+теги). Потребує ENABLE_CONTEXT_API."""
        return cli.context_ingest(summary, kind)

    def code(text: str, target: str = "local") -> dict[str, Any]:
        """Задача coding-агенту JARVIS (Стовп B). Виконується на РЕАЛЬНІЙ машині через hostagent →
        мутуючі дії вимагають підтвердження (S4): перевір `confirm_pending`, апрув — `confirm_approve`.
        target: local (рідний агент) | claude (за прапором). НІКОЛИ не апрувиться автоматично."""
        return cli.code(text, target)

    def computer(text: str) -> dict[str, Any]:
        """Computer-use дія на PC через JARVIS (tier-ladder S5). Мутуючі дії → confirm-гейт (S4).
        Потребує ENABLE_COMPUTER_USE. Апрув — окремо через `confirm_approve`, ніколи не авто."""
        return cli.computer(text)

    def confirm_pending() -> dict[str, Any]:
        """Чи є дія, що чекає підтвердження (S4), і її опис."""
        return cli.confirm_pending()

    def confirm_approve(code: str) -> dict[str, Any]:
        """Підтвердити (людиною) дію, що очікує — за кодом із `confirm_pending`. S4 human-in-the-loop."""
        return cli.confirm_approve(code)

    def confirm_cancel() -> dict[str, Any]:
        """Скасувати дію, що очікує підтвердження."""
        return cli.confirm_cancel()

    def mcp_list() -> dict[str, Any]:
        """Які downstream MCP-сервери знає JARVIS (керований хаб). Потребує ENABLE_MCP_HUB."""
        return cli.mcp_list()

    def mcp_call(server: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Викликати tool downstream MCP-сервера через JARVIS-хаб (auth+політика попереду). ENABLE_MCP_HUB."""
        return cli.mcp_call(server, tool, arguments)

    # Імперативна реєстрація (не `@`-декоратор): декоратор-синтаксис робить функцію untyped (mypy
    # strict). Явні виклики (а не цикл по словнику) — бо функції мають різні сигнатури.
    server.tool(name="whoami")(whoami)
    server.tool(name="chat")(chat)
    server.tool(name="context_search")(context_search)
    server.tool(name="context_recent")(context_recent)
    server.tool(name="context_ingest")(context_ingest)
    server.tool(name="code")(code)
    server.tool(name="computer")(computer)
    server.tool(name="confirm_pending")(confirm_pending)
    server.tool(name="confirm_approve")(confirm_approve)
    server.tool(name="confirm_cancel")(confirm_cancel)
    server.tool(name="mcp_list")(mcp_list)
    server.tool(name="mcp_call")(mcp_call)
    return server


def main() -> None:
    # Транспорт: stdio (дефолт, S1 локально) | http (streamable-http) | sse — AP-7.5a.
    transport = (os.environ.get("JARVIS_MCP_TRANSPORT") or "stdio").strip().lower()
    server = build_server()
    if transport in ("http", "streamable-http", "streamable_http"):
        server.run(transport="streamable-http")
    elif transport == "sse":
        server.run(transport="sse")
    else:
        server.run()  # stdio


if __name__ == "__main__":
    main()
