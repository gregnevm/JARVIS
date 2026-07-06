"""erp_sa — MCP-адаптер автозаповнення ERP Sparrow-Avia (stdio/http сервер).

Робить із рутини «переносити дані з документа в ERP-форму руками» один MCP-виклик:
`autofill` = ingest → recognize (локальний JARVIS) → inspect_form → map → fill → confirm-превʼю.
Заповнення йде через **Chrome-міст** (`/api/v1/chrome/*`) у РЕАЛЬНОМУ браузері юзера, який уже за
VPN і залогінений в ERP → нуль VPN/креденшелів на сервері (S1).

Архітектура (Ports & Adapters, концепт §3):
  * Engine (цей файл) — generic пайплайн + порти `recognize`/`locate`/`map`/`fill`/`audit`.
    Нуль рядка «Sparrow»: уся ERP-конкретика — у adapters/sparrow-avia/manifest.json.
  * Adapter (sparrow-avia) — route_map / field_aliases / allowlist (drift ловить tests/).

Тестованість (P8): ядро (`GatewayConfig`/`GatewayClient`/pure-функції) не імпортує `mcp` —
FastMCP підвантажується лазі в `build_server()`, тож юніти ганяються без MCP-SDK і без мережі.

Безпека:
  * S1: recognize локальний; audit — лише метадані (anti-leak; документи = PII); redaction перед виходом.
  * S4: `fill`/`autofill` тільки ЗАПОВНЮЮТЬ; фінальний submit — людина/`confirm_approve`, ніколи не авто.
  * Blast-radius: кожна DOM-дія звіряє `location.href` з allowlist (deny-wins, fail-closed).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

_DEFAULT_BASE_URL = "http://localhost:8000"  # S1: локальний інстанс за дефолтом
_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "adapters" / "sparrow-avia" / "manifest.json"

# Живу form-schema знімає extension (CSP-safe дія `schema`) і віддає JSON-рядок —
# `_coerce_schema` толерантно приводить його (str|list) до list[dict].
def _coerce_schema(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, dict)]


class GatewayConfigError(RuntimeError):
    """Порт `endpoint`/`auth` не заповнений → адаптер відмовляється стартувати (fail-fast)."""


class BlastRadiusError(RuntimeError):
    """DOM-дія поза allowlisted ERP-роутом (deny-wins, fail-closed)."""


class ChromeBridgeError(RuntimeError):
    """Chrome-міст не повернув результат (extension не піднято / таймаут). Ніколи не мокаємо тихо."""


class RecognizeError(RuntimeError):
    """Розпізнавання неможливе (непідтримуваний ввід / vision вимкнено)."""


# --- Audit (порт `audit`) — реюз SSOT JsonlLog без важкого jarvis_core-дерева ----

class _FallbackJsonlLog:
    def __init__(self, path: str | Path) -> None:
        self._p = Path(path)
        self._p.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> int:
        with self._p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return 0


def _resolve_jsonl_log_cls() -> Any:
    """Завантажуємо `jarvis_core/llm/jsonl_log.py:JsonlLog` прямо з файлу (оминаючи __init__)."""
    try:
        repo_root = Path(__file__).resolve().parents[4]  # engine→erp_sa→skills→.claude→ROOT
        mod_path = repo_root / "jarvis_core" / "llm" / "jsonl_log.py"
        if mod_path.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("_erp_sa_jsonl", mod_path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.JsonlLog
    except Exception:  # noqa: BLE001 — audit ніколи не валить адаптер
        pass
    return _FallbackJsonlLog


def make_audit(path: str | Path) -> Callable[..., None]:
    logger = _resolve_jsonl_log_cls()(path)

    def audit(tool: str, summary: str, tags: list[str], status: str = "ok") -> None:
        try:
            logger.append({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tool": tool, "summary": summary, "tags": tags, "status": status,
            })
        except Exception:  # noqa: BLE001
            pass

    return audit


def _default_audit_path() -> Path:
    try:
        return Path(__file__).resolve().parents[4] / "data" / "logs" / "erp_sa.jsonl"
    except Exception:  # noqa: BLE001
        return Path("erp_sa.jsonl")


def _repo_env_password(env_path: Path | None = None) -> str | None:
    """Пароль gateway із co-located репо-`.env` (PLATFORM_PASSWORD > ADMIN_PANEL_PASSWORD)."""
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
    except Exception:  # noqa: BLE001
        return None


# --- Redaction (порт S1) — скраб секретів перед виходом у хост-AI -----------------

def _make_redactor() -> Callable[[str], str]:
    try:
        from jarvis_core.passport.redaction import _DEFAULT_RULES, Redactor

        _DROP = {"card", "iban", "otp"}  # числова PII → false-positive на ID/UUID/числах
        return Redactor([r for r in _DEFAULT_RULES if r.name not in _DROP]).redact
    except Exception:  # noqa: BLE001
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


# --- Adapter (sparrow-avia): route_map / field_aliases / allowlist ---------------

@dataclass(frozen=True)
class Adapter:
    base_url: str
    allowlist: tuple[str, ...]
    field_aliases: dict[str, list[str]]
    route_map: dict[str, str]

    @classmethod
    def load(cls, path: Path | None = None) -> "Adapter":
        p = path or _MANIFEST_PATH
        data = json.loads(p.read_text(encoding="utf-8"))
        aliases = {k: list(v) for k, v in (data.get("field_aliases") or {}).items()
                   if not k.startswith("_")}
        routes = {k: str(v) for k, v in (data.get("route_map") or {}).items()
                  if not k.startswith("_")}
        return cls(
            base_url=str(data.get("base_url") or ""),
            allowlist=tuple(data.get("allowlist") or []),
            field_aliases=aliases,
            route_map=routes,
        )

    def canonical_fields(self) -> list[str]:
        return list(self.field_aliases.keys())


def url_allowed(url: str, allowlist: tuple[str, ...] | list[str]) -> bool:
    """Blast-radius: URL має збігтися хоча б з одним allow-патерном. Порожній allowlist → deny-all."""
    if not url or not allowlist:
        return False
    u = url.split("#", 1)[0].split("?", 1)[0]
    return any(fnmatch.fnmatch(u, pat) or fnmatch.fnmatch(url, pat) for pat in allowlist)


# --- map (порт `map`): поля документа × form-schema → FormFill -------------------

def map_fields(
    fields: Mapping[str, Any],
    form_schema: list[dict[str, Any]],
    field_aliases: Mapping[str, list[str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Зіставляє розпізнані канонічні поля з живими полями форми через синоніми.

    Повертає (form_fill[{selector,value,source_field}], unmapped[canonical]).
    Невідоме/порожнє → в unmapped; НІКОЛИ не заливаємо здогад."""
    fill: list[dict[str, Any]] = []
    unmapped: list[str] = []
    used_selectors: set[str] = set()
    for canonical, value in fields.items():
        if value is None or str(value).strip() == "":
            continue
        aliases = {a.lower() for a in field_aliases.get(canonical, [])}
        aliases.add(canonical.lower())
        match = _match_form_field(aliases, form_schema, used_selectors)
        if match is None:
            unmapped.append(canonical)
            continue
        used_selectors.add(match["selector"])
        fill.append({"selector": match["selector"], "value": str(value), "source_field": canonical})
    return fill, unmapped


def _match_form_field(
    aliases: set[str], form_schema: list[dict[str, Any]], used: set[str],
) -> dict[str, Any] | None:
    for field in form_schema:
        sel = str(field.get("selector") or "")
        if not sel or sel in used:
            continue
        haystacks = [str(field.get(k) or "").lower() for k in ("name", "id", "label")]
        for h in haystacks:
            if h and (h in aliases or any(a in h or h in a for a in aliases)):
                return field
    return None


# --- recognize (порт `recognize`): документ → структуровані поля -----------------

def _parse_json_block(text: str) -> dict[str, Any]:
    """Толерантний парс першого JSON-обʼєкта з відповіді LLM (моделі часто обгортають у прозу)."""
    text = text.strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start:end + 1] if start != -1 and end > start else None
    if not candidate:
        return {}
    try:
        out = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return out if isinstance(out, dict) else {}


def build_recognize_prompt(text: str, canonical_fields: list[str]) -> str:
    fields_line = ", ".join(canonical_fields) if canonical_fields else "(усі знайдені поля)"
    return (
        "Витягни структуровані дані з документа нижче для заповнення ERP-форми. "
        "Поверни ЛИШЕ валідний JSON (без пояснень) з такими ключами (пропущені лиши порожніми): "
        f"{fields_line}. Додатково: \"doc_type\" (тип документа) і \"confidence\" (0..1). "
        "Не вигадуй значень, яких немає в документі.\n\n=== ДОКУМЕНТ ===\n" + text
    )


# --- ingest (порт `ingest`): цифровий файл → текст ------------------------------

_TEXT_EXT = {".txt", ".md", ".log"}
_CSV_EXT = {".csv", ".tsv"}
_SCAN_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _import_optional(name: str, hint: str) -> Any:
    import importlib
    try:
        return importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        raise RecognizeError(hint) from exc


def extract_source_text(path: str | Path) -> str:
    """Цифровий файл → текст. Скан/фото та pdf без текстового шару → RecognizeError (шлях vision — P2)."""
    p = Path(path)
    if not p.is_file():
        raise RecognizeError(f"file not found: {p}")
    ext = p.suffix.lower()
    if ext in _TEXT_EXT:
        return p.read_text(encoding="utf-8", errors="ignore")
    if ext in _CSV_EXT:
        import csv
        with p.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            return "\n".join("\t".join(row) for row in csv.reader(f))
    if ext == ".pdf":
        pdf = _import_optional("pypdf", "pdf: встанови pypdf")
        text = "\n".join((pg.extract_text() or "") for pg in pdf.PdfReader(str(p)).pages)
        if not text.strip():
            raise RecognizeError("pdf без текстового шару (ймовірно скан) — потрібен vision (P2)")
        return text
    if ext == ".docx":
        docx = _import_optional("docx", "docx: встанови python-docx")
        d = docx.Document(str(p))
        parts = [para.text for para in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append("\t".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext in (".xlsx", ".xlsm"):
        pyxl = _import_optional("openpyxl", "xlsx: встанови openpyxl")
        wb = pyxl.load_workbook(str(p), read_only=True, data_only=True)
        lines: list[str] = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                lines.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(lines)
    if ext in _SCAN_EXT:
        raise RecognizeError(f"{ext}: скан/фото — потрібен vision (P2; постав OLLAMA_MODEL_VISION)")
    raise RecognizeError(f"unsupported file type: {ext}")


# --- Config (порти `endpoint` + `auth`) ------------------------------------------

@dataclass(frozen=True)
class GatewayConfig:
    base_url: str
    api_key: str | None
    basic_user: str
    basic_password: str | None
    timeout: float
    audit_path: str
    redact: bool
    poll_attempts: int
    poll_interval: float

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "GatewayConfig":
        e: Mapping[str, str] = os.environ if env is None else env
        base_url = (e.get("ERP_SA_BASE_URL") or e.get("JARVIS_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        api_key = e.get("ERP_SA_API_KEY") or e.get("JARVIS_API_KEY") or None
        basic_user = e.get("ERP_SA_BASIC_USER") or e.get("JARVIS_BASIC_USER") or "admin"
        basic_password = (
            e.get("ERP_SA_BASIC_PASSWORD")
            or e.get("JARVIS_BASIC_PASSWORD")
            or e.get("PLATFORM_PASSWORD")
            or e.get("ADMIN_PANEL_PASSWORD")
            or None
        )
        if not base_url:
            raise GatewayConfigError("endpoint port unfilled: base_url is empty")
        if env is None and not api_key and not basic_password:
            basic_password = _repo_env_password() or None
        if not api_key and not basic_password:
            raise GatewayConfigError(
                "auth port unfilled: set ERP_SA_API_KEY/JARVIS_API_KEY (Bearer) "
                "or *_BASIC_PASSWORD / PLATFORM_PASSWORD (Basic), or run co-located with a repo .env"
            )
        try:
            timeout = float(e.get("ERP_SA_TIMEOUT") or "60")
            poll_attempts = int(e.get("ERP_SA_POLL_ATTEMPTS") or "40")
            poll_interval = float(e.get("ERP_SA_POLL_INTERVAL") or "0.5")
        except ValueError as exc:
            raise GatewayConfigError("ERP_SA_TIMEOUT/POLL_* must be numbers") from exc
        audit_path = e.get("ERP_SA_AUDIT") or str(_default_audit_path())
        redact = (e.get("ERP_SA_REDACT") or e.get("JARVIS_REDACT") or "1").strip().lower() \
            not in ("0", "false", "no", "off")
        return cls(base_url, api_key, basic_user, basic_password, timeout,
                   audit_path, redact, poll_attempts, poll_interval)

    def httpx_auth(self) -> httpx.Auth | None:
        if self.api_key:
            return None
        if self.basic_password:
            return httpx.BasicAuth(self.basic_user, self.basic_password)
        return None

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}


def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


# --- Client (gateway I/O: chat, chrome-міст, confirm) ----------------------------

class GatewayClient:
    """Тонкий httpx-клієнт до локального gateway. Chat (recognize), Chrome-міст (fill), confirm (S4)."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        audit: Callable[..., None] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._cfg = config
        self._audit = audit or make_audit(config.audit_path)
        self._sleep = sleep or time.sleep
        self._scrub: Callable[[str], str] | None = _make_redactor() if config.redact else None
        self._http = httpx.Client(
            base_url=config.base_url, timeout=config.timeout,
            auth=config.httpx_auth(), headers=config.headers(), transport=transport,
        )

    def __enter__(self) -> "GatewayClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.post(path, json=body)
        resp.raise_for_status()
        return self._scrubbed(_as_dict(resp.json()))

    def _get(self, path: str) -> dict[str, Any]:
        resp = self._http.get(path)
        resp.raise_for_status()
        return self._scrubbed(_as_dict(resp.json()))

    def _scrubbed(self, data: dict[str, Any]) -> dict[str, Any]:
        if self._scrub is not None:
            return _as_dict(_redact_value(data, self._scrub))
        return data

    # --- identity (порт readiness) ---
    def whoami(self) -> dict[str, Any]:
        return self._get("/api/v1/whoami")

    # --- chat (порт recognize LLM) ---
    def chat(self, text: str, mode: str = "chat") -> dict[str, Any]:
        data = self._post("/api/v1/chat", {"text": text, "mode": mode})
        self._audit("chat", f"recognize.chat mode={mode} chars_in={len(text)}",
                    ["kind:erp_sa-call", "tool:chat", "pillar:A"])
        return data

    # --- chrome-міст (порт fill/locate) — command → poll result ---
    def chrome(self, action: str, *, selector: str | None = None, value: str | None = None,
               url: str | None = None, script: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"action": action}
        for k, v in (("selector", selector), ("value", value), ("url", url), ("script", script)):
            if v is not None:
                body[k] = v
        queued = self._post("/api/v1/chrome/command", body)
        cmd_id = str(queued.get("id") or "")
        if not cmd_id:
            raise ChromeBridgeError("chrome/command returned no id")
        for _ in range(self._cfg.poll_attempts):
            res = self._get(f"/api/v1/chrome/result/{cmd_id}")
            if res.get("status") == "done":
                self._audit("chrome", f"chrome action={action}",
                            ["kind:erp_sa-call", "tool:chrome", f"action:{action}", "pillar:C"])
                return {"ok": bool(res.get("ok", True)), "result": res.get("result")}
            self._sleep(self._cfg.poll_interval)
        raise ChromeBridgeError(f"chrome action={action}: no result (extension up?)")

    def current_url(self) -> str:
        out = self.chrome("location")  # CSP-safe first-class дія (не eval)
        return str(out.get("result") or "")

    # --- confirm (порт confirm_gate, S4) — реюз gateway ---
    def confirm_pending(self) -> dict[str, Any]:
        data = self._get("/api/v1/confirm/pending")
        self._audit("confirm_pending", f"confirm_pending pending={data.get('pending')}",
                    ["kind:erp_sa-call", "tool:confirm_pending", "pillar:B"])
        return data

    def confirm_approve(self, code: str) -> dict[str, Any]:
        data = self._post("/api/v1/confirm/approve", {"code": code})
        self._audit("confirm_approve", f"confirm_approve code_len={len(code)}",
                    ["kind:erp_sa-call", "tool:confirm_approve", "pillar:B"], "human-approved")
        return data

    def confirm_cancel(self) -> dict[str, Any]:
        data = self._post("/api/v1/confirm/cancel", {})
        self._audit("confirm_cancel", "confirm_cancel",
                    ["kind:erp_sa-call", "tool:confirm_cancel", "pillar:B"])
        return data


# --- Engine (generic оркестрація портів) -----------------------------------------

class Engine:
    """Generic пайплайн autofill. Нуль ERP-конкретики — усе з Adapter (DR2)."""

    def __init__(self, client: GatewayClient, adapter: Adapter,
                 audit: Callable[..., None] | None = None) -> None:
        self._cli = client
        self._adp = adapter
        self._audit = audit or make_audit(client._cfg.audit_path)  # noqa: SLF001 — той самий sink

    # порт readiness — діагностика live-налаштування (чому autofill не поїде)
    def ready(self) -> dict[str, Any]:
        out: dict[str, Any] = {"gateway": False, "chrome_bridge": False,
                               "on_allowlisted_page": False, "current_url": ""}
        try:
            who = self._cli.whoami()
            out["gateway"] = True
            out["identity"] = {"org_id": who.get("org_id"), "via": who.get("via")}
        except Exception as exc:  # noqa: BLE001 — діагностика, не валимо
            out["gateway_error"] = type(exc).__name__
        try:
            url = self._cli.current_url()
            out["chrome_bridge"] = True
            out["current_url"] = url
            out["on_allowlisted_page"] = url_allowed(url, self._adp.allowlist)
        except Exception as exc:  # noqa: BLE001
            out["chrome_bridge_error"] = type(exc).__name__
        out["ready"] = bool(out["gateway"] and out["chrome_bridge"])
        out["allowlist"] = list(self._adp.allowlist)
        return out

    # порт locate — тип документа → цільова ERP-сторінка (route_map)
    def locate(self, doc_type: str) -> dict[str, Any]:
        route = self._adp.route_map.get(doc_type)
        url = f"{self._adp.base_url}{route}" if route else ""
        return {"doc_type": doc_type, "url": url, "known": bool(route),
                "allowed": url_allowed(url, self._adp.allowlist) if url else False}

    # порт ingest+recognize
    def recognize(self, text: str = "", *, source_path: str = "") -> dict[str, Any]:
        src_kind = "text"
        content = text
        if source_path:
            content = extract_source_text(source_path)
            src_kind = f"file{Path(source_path).suffix.lower()}"
        if not content or not content.strip():
            raise RecognizeError("empty source: give text or a supported file (source_path)")
        prompt = build_recognize_prompt(content, self._adp.canonical_fields())
        reply = str(self._cli.chat(prompt, mode="chat").get("reply") or "")
        parsed = _parse_json_block(reply)
        fields = {k: v for k, v in parsed.items() if k not in ("doc_type", "confidence")}
        result = {
            "doc_type": parsed.get("doc_type", ""),
            "confidence": parsed.get("confidence", 0),
            "fields": fields,
        }
        self._audit("recognize",
                    f"recognize src={src_kind} doc_type={result['doc_type']} "
                    f"fields={len(fields)} conf={result['confidence']}",
                    ["kind:erp_sa-step", "step:recognize", "pillar:A"])
        return result

    # порт locate/inspect
    def inspect_form(self, url: str | None = None) -> list[dict[str, Any]]:
        if url:
            self._ensure_url_allowed(url)
            self._cli.chrome("navigate", url=url)
        else:
            self._ensure_current_allowed()
        out = self._cli.chrome("schema")  # CSP-safe; extension повертає JSON-рядок
        fields = _coerce_schema(out.get("result"))
        self._audit("inspect_form", f"inspect_form fields={len(fields)}",
                    ["kind:erp_sa-step", "step:locate", "pillar:A"])
        return fields

    # порти map + fill + confirm-превʼю
    def autofill(self, text: str = "", *, source_path: str = "",
                 url: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        recognized = self.recognize(text, source_path=source_path)
        form_schema = self.inspect_form(url)
        form_fill, unmapped = map_fields(recognized["fields"], form_schema, self._adp.field_aliases)
        preview = {
            "doc_type": recognized["doc_type"],
            "confidence": recognized["confidence"],
            "form_fill": form_fill,
            "unmapped": unmapped,
            "dry_run": dry_run,
        }
        if dry_run:
            preview["note"] = "dry_run: нічого не заповнено. Прибери dry_run, щоб заповнити (submit усе одно за людиною, S4)."
            return preview
        result = self.fill(form_fill)
        preview.update(result)
        preview["note"] = "Поля заповнено. Перевір і натисни «Зберегти» сам — адаптер не сабмітить (S4)."
        return preview

    # порт fill (blast-radius перед кожним заповненням)
    def fill(self, form_fill: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_current_allowed()
        filled: list[str] = []
        skipped: list[dict[str, Any]] = []
        for item in form_fill:
            selector = str(item.get("selector") or "")
            value = str(item.get("value") or "")
            if not selector:
                skipped.append({"item": item, "reason": "no selector"})
                continue
            out = self._cli.chrome("fill", selector=selector, value=value)
            if out.get("ok"):
                filled.append(selector)
            else:
                skipped.append({"selector": selector, "reason": "fill not ok"})
        self._audit("fill", f"fill filled={len(filled)} skipped={len(skipped)}",
                    ["kind:erp_sa-step", "step:fill", "pillar:C"])
        return {"filled": filled, "skipped": skipped}

    # --- blast-radius (S5, deny-wins, fail-closed) ---
    def _ensure_url_allowed(self, url: str) -> None:
        if not url_allowed(url, self._adp.allowlist):
            raise BlastRadiusError(f"url outside allowlist: {url}")

    def _ensure_current_allowed(self) -> None:
        current = self._cli.current_url()
        if not url_allowed(current, self._adp.allowlist):
            raise BlastRadiusError(f"current page outside allowlist: {current or '(unknown)'}")


# --- MCP server (порт `capabilities`; FastMCP лазі) ------------------------------

def build_server(engine: Engine | None = None, client: GatewayClient | None = None) -> Any:
    """Будує FastMCP-сервер `erp_sa`. `mcp` імпортується тут (lazy, тестовність ядра)."""
    from mcp.server.fastmcp import FastMCP

    if engine is None:
        adapter = Adapter.load()
        cli = client if client is not None else GatewayClient(GatewayConfig.from_env())
        engine = Engine(cli, adapter)
    eng = engine
    server = FastMCP("erp_sa")

    def ready() -> dict[str, Any]:
        """Діагностика готовності: gateway (auth), Chrome-міст (extension), чи на allowlisted ERP-сторінці.
        Клич ПЕРШИМ — покаже, що підняти перед autofill (VPN / gateway :8000 / extension)."""
        return eng.ready()

    def locate(doc_type: str) -> dict[str, Any]:
        """Тип документа → цільовий ERP-URL із route_map адаптера (передай його в inspect_form/autofill як url)."""
        return eng.locate(doc_type)

    def recognize(text: str = "", source_path: str = "") -> dict[str, Any]:
        """Розпізнати документ → структуровані поля. Без заповнення. Дай `text` АБО `source_path`
        (txt/csv/pdf/docx/xlsx). Локальний інференс JARVIS (S1). Скани/фото — P2 (vision)."""
        return eng.recognize(text, source_path=source_path)

    def inspect_form(url: str = "") -> dict[str, Any]:
        """Зняти живу схему форми (селектори+лейбли) через Chrome-міст. url='' = поточна сторінка.
        Годує map, анти-дрейф проти змін ERP. Blast-radius: лише allowlisted роути."""
        return {"form_schema": eng.inspect_form(url or None)}

    def autofill(text: str = "", source_path: str = "", url: str = "",
                 dry_run: bool = True) -> dict[str, Any]:
        """Головний happy-path: recognize→inspect→map→(fill). Дай `text` АБО `source_path`.
        dry_run=true (дефолт) лише показує мапу. S4: фінальний submit — за людиною, адаптер не сабмітить сам."""
        return eng.autofill(text, source_path=source_path, url=url or None, dry_run=dry_run)

    def fill(form_fill: list[dict[str, Any]]) -> dict[str, Any]:
        """Низькорівнево заповнити за готовою мапою [{selector,value}]. Blast-radius перевіряється."""
        return eng.fill(form_fill)

    def confirm_pending() -> dict[str, Any]:
        """Чи є дія агента, що чекає підтвердження (S4)."""
        return eng._cli.confirm_pending()  # noqa: SLF001

    def confirm_approve(code: str) -> dict[str, Any]:
        """Людський апрув дії, що очікує — за кодом із confirm_pending (S4)."""
        return eng._cli.confirm_approve(code)  # noqa: SLF001

    def confirm_cancel() -> dict[str, Any]:
        """Скасувати дію, що очікує підтвердження."""
        return eng._cli.confirm_cancel()  # noqa: SLF001

    server.tool(name="ready")(ready)
    server.tool(name="locate")(locate)
    server.tool(name="recognize")(recognize)
    server.tool(name="inspect_form")(inspect_form)
    server.tool(name="autofill")(autofill)
    server.tool(name="fill")(fill)
    server.tool(name="confirm_pending")(confirm_pending)
    server.tool(name="confirm_approve")(confirm_approve)
    server.tool(name="confirm_cancel")(confirm_cancel)
    return server


def main() -> None:
    transport = (os.environ.get("ERP_SA_MCP_TRANSPORT") or "stdio").strip().lower()
    server = build_server()
    if transport in ("http", "streamable-http", "streamable_http"):
        server.run(transport="streamable-http")
    elif transport == "sse":
        server.run(transport="sse")
    else:
        server.run()  # stdio


if __name__ == "__main__":
    main()
