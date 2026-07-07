"""ai_tester — MCP-рушій автономного самотестування фіч платформи (stdio/http сервер).

Робить із рутини «прогнати всі фічі руками» один MCP-виклик: `run` = scenario → source →
oracle → вердикти; `loop_run` = bounded цикл test → dispatch-fix (coder) / verify (computer-use)
→ retest. Джерело даних — ланцюжок **декораторів** над реальним gateway: `ReplaySource`
(підміна відповіді фікстурою) / `FaultSource` (інʼєкція збою) / `RecordingSource` (запис
фікстур) — симуляція ендпоінта без жодної зміни бекенду (S2).

Архітектура (Ports & Adapters, як kaizen/erp_sa):
  * Engine (цей файл) — generic: порти `endpoint`/`auth`/`source`/`scenario`/`oracle`/
    `dispatch`/`loop`/`report`/`confirm_gate`/`audit`. Нуль JARVIS-конкретики: реєстр фіч —
    у adapters/jarvis/manifest.json.
  * Adapter (jarvis) — фічі (ендпоінт+oracle+sim+on_fail); drift ловить tests/.
  * «Всі модулі — MCP»: кожен порт експонований 1:1 MCP-тулом; ремедіація бʼє в ті самі
    endpoint-и, що стоять за mcp__jarvis__code / mcp__jarvis__computer. Жодного CLI-only входу.

Тестованість (P8): ядро не імпортує `mcp` — FastMCP підвантажується лазі в `build_server()`,
тож юніти ганяються без MCP-SDK і без мережі (httpx.MockTransport).

Безпека:
  * S1: інференс/тести локальні; audit і run-звіти — лише метадані (без сирих відповідей);
    redaction перед виходом. Виняток: `record`-режим свідомо пише (вже зредаговані) тіла
    відповідей у recordings-* — вони під .gitignore, у git-дерево не їдуть.
  * S4: `dispatch_fix`/`verify_ui`/`loop_run` лише ДИСПАТЧАТЬ ремедіацію — мутуючий крок чекає
    людського `confirm_approve`; рушій НІКОЛИ не апрувить сам (луп зупиняється в awaiting_confirm).
  * Suite за замовчуванням не чіпає mutating-фічі (code_task/driver_exec) — лише явним викликом.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

_DEFAULT_BASE_URL = "http://localhost:8000"  # S1: локальний інстанс за дефолтом
_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "adapters" / "jarvis" / "manifest.json"

# Маркер S4-підтвердження у відповідях coder/computer (gateway/app/bot/computer.py).
_CONFIRM_RE = re.compile(r"\[\[COMPUTER_(?:ADMIN_)?CONFIRM:([A-Za-z0-9_-]+)\]\]")

_FAULTS = ("http_500", "http_404", "timeout", "malformed", "empty_reply")


class TesterConfigError(RuntimeError):
    """Порт `endpoint`/`auth` не заповнений → рушій відмовляється стартувати (fail-fast)."""


class ScenarioError(RuntimeError):
    """Невідома фіча/fault — узгодь виклик із adapters/*/manifest.json (порт `scenario`)."""


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
        repo_root = Path(__file__).resolve().parents[4]  # engine→ai_tester→skills→.claude→ROOT
        mod_path = repo_root / "jarvis_core" / "llm" / "jsonl_log.py"
        if mod_path.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("_ai_tester_jsonl", mod_path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.JsonlLog
    except Exception:  # noqa: BLE001 — audit ніколи не валить рушій
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
        return Path(__file__).resolve().parents[4] / "data" / "logs" / "ai_tester.jsonl"
    except Exception:  # noqa: BLE001
        return Path("ai_tester.jsonl")


def _default_artifacts_dir() -> Path:
    try:
        return Path(__file__).resolve().parents[4] / "data" / "artifacts" / "ai_tester"
    except Exception:  # noqa: BLE001
        return Path("ai_tester_artifacts")


def _repo_env_password(env_path: Path | None = None) -> str | None:
    """Пароль gateway із co-located репо-`.env` (PLATFORM_PASSWORD > ADMIN_PANEL_PASSWORD)."""
    try:
        p = env_path if env_path is not None else (Path(__file__).resolve().parents[4] / ".env")
        if not p.is_file():
            return None
        found: dict[str, str] = {}
        # utf-8-sig: PowerShell любить відрощувати BOM у .env — без цього ключ на першому рядку губиться.
        for line in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
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

def _load_redaction_module() -> Any:
    """SSOT `jarvis_core/passport/redaction.py` БЕЗ важкого `jarvis_core/__init__` (facade/ollama).

    У канонічному запуску (`.venv python .claude/.../server.py`) jarvis_core не на sys.path —
    plain import тихо деградував би до слабкого фолбека. Тому: спершу plain import (як в erp_sa/
    jarvis), а як ні — збираємо синтетичний пакет із файлів (redaction має відносний `.models`)."""
    try:
        from jarvis_core.passport import redaction  # jarvis_core встановлений / вже на path
        return redaction
    except Exception:  # noqa: BLE001
        pass
    import importlib.util
    import sys
    import types

    pkg_dir = Path(__file__).resolve().parents[4] / "jarvis_core" / "passport"
    pkg = types.ModuleType("_ai_tester_passport")
    pkg.__path__ = [str(pkg_dir)]
    sys.modules["_ai_tester_passport"] = pkg
    loaded: dict[str, Any] = {}
    for name in ("models", "redaction"):  # models першим — redaction робить `from .models import`
        spec = importlib.util.spec_from_file_location(f"_ai_tester_passport.{name}",
                                                      pkg_dir / f"{name}.py")
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load jarvis_core/passport/{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_ai_tester_passport.{name}"] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded["redaction"]


def _make_redactor() -> Callable[[str], str]:
    try:
        redaction = _load_redaction_module()

        _DROP = {"card", "iban", "otp"}  # числова PII → false-positive на ID/UUID/числах
        return redaction.Redactor(
            [r for r in redaction._DEFAULT_RULES if r.name not in _DROP]).redact
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


def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


# --- Config (порти `endpoint` + `auth`) ------------------------------------------

@dataclass(frozen=True)
class TesterConfig:
    base_url: str
    api_key: str | None
    basic_user: str
    basic_password: str | None
    timeout: float
    audit_path: str
    artifacts_dir: str
    redact: bool
    max_rounds: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TesterConfig":
        e: Mapping[str, str] = os.environ if env is None else env
        base_url = (e.get("AI_TESTER_BASE_URL") or e.get("JARVIS_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        api_key = e.get("AI_TESTER_API_KEY") or e.get("JARVIS_API_KEY") or None
        basic_user = e.get("AI_TESTER_BASIC_USER") or e.get("JARVIS_BASIC_USER") or "admin"
        basic_password = (
            e.get("AI_TESTER_BASIC_PASSWORD")
            or e.get("JARVIS_BASIC_PASSWORD")
            or e.get("PLATFORM_PASSWORD")
            or e.get("ADMIN_PANEL_PASSWORD")
            or None
        )
        if not base_url:
            raise TesterConfigError("endpoint port unfilled: base_url is empty")
        if env is None and not api_key and not basic_password:
            basic_password = _repo_env_password() or None
        if not api_key and not basic_password:
            raise TesterConfigError(
                "auth port unfilled: set AI_TESTER_API_KEY/JARVIS_API_KEY (Bearer) "
                "or *_BASIC_PASSWORD / PLATFORM_PASSWORD (Basic), or run co-located with a repo .env"
            )
        try:
            timeout = float(e.get("AI_TESTER_TIMEOUT") or "120")
            max_rounds = int(e.get("AI_TESTER_MAX_ROUNDS") or "3")
        except ValueError as exc:
            raise TesterConfigError("AI_TESTER_TIMEOUT/AI_TESTER_MAX_ROUNDS must be numbers") from exc
        if max_rounds < 1:
            raise TesterConfigError("AI_TESTER_MAX_ROUNDS must be >= 1")
        audit_path = e.get("AI_TESTER_AUDIT") or str(_default_audit_path())
        artifacts_dir = e.get("AI_TESTER_ARTIFACTS") or str(_default_artifacts_dir())
        redact = (e.get("AI_TESTER_REDACT") or e.get("JARVIS_REDACT") or "1").strip().lower() \
            not in ("0", "false", "no", "off")
        return cls(base_url, api_key, basic_user, basic_password, timeout,
                   audit_path, artifacts_dir, redact, max_rounds)

    def httpx_auth(self) -> httpx.Auth | None:
        if self.api_key:
            return None
        if self.basic_password:
            return httpx.BasicAuth(self.basic_user, self.basic_password)
        return None

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}


# --- Adapter (порт `scenario`): реєстр фіч із manifest ----------------------------

@dataclass(frozen=True)
class Feature:
    name: str
    title: str
    method: str
    path: str
    request: dict[str, Any] | None
    gate_flag: str
    gated_statuses: tuple[int, ...]
    mutating: bool
    oracle: dict[str, Any]
    sim: dict[str, Any] | None
    dispatch_kind: str  # code | computer
    on_fail_hint: str


@dataclass(frozen=True)
class Adapter:
    profile: str
    base_url_default: str
    features: dict[str, Feature]

    @classmethod
    def load(cls, path: Path | None = None) -> "Adapter":
        p = path or _MANIFEST_PATH
        data = json.loads(p.read_text(encoding="utf-8"))
        feats: dict[str, Feature] = {}
        for name, raw in (data.get("features") or {}).items():
            if name.startswith("_") or not isinstance(raw, dict):
                continue
            on_fail = _as_dict(raw.get("on_fail"))
            feats[name] = Feature(
                name=name,
                title=str(raw.get("title") or name),
                method=str(raw.get("method") or "GET").upper(),
                path=str(raw.get("path") or ""),
                request=raw.get("request") if isinstance(raw.get("request"), dict) else None,
                gate_flag=str(raw.get("gate_flag") or ""),
                gated_statuses=tuple(int(s) for s in (raw.get("gated_statuses") or [])),
                mutating=bool(raw.get("mutating", False)),
                oracle=_as_dict(raw.get("oracle")),
                sim=raw.get("sim") if isinstance(raw.get("sim"), dict) else None,
                dispatch_kind=str(on_fail.get("dispatch") or "code"),
                on_fail_hint=str(on_fail.get("hint") or ""),
            )
        return cls(
            profile=str(data.get("profile") or ""),
            base_url_default=str(data.get("base_url_default") or ""),
            features=feats,
        )

    def feature(self, name: str) -> Feature:
        feat = self.features.get(name)
        if feat is None:
            raise ScenarioError(f"unknown feature: {name!r} (see adapters/{self.profile}/manifest.json)")
        return feat


# --- Gateway I/O (порти `endpoint`/`auth`/`dispatch`) -----------------------------

@dataclass(frozen=True)
class SourceResult:
    """Уніфікований результат джерела: HTTP-статус + JSON-тіло + транспортна помилка + тайминг.
    `injected=True` ставить FaultSource — інʼєктований збій не має маскуватись під gate (oracle)."""
    status: int
    data: dict[str, Any]
    error: str = ""
    elapsed_ms: int = 0
    injected: bool = False


class GatewayHttp:
    """Тонкий httpx-клієнт до gateway. НЕ кидає на 4xx/5xx — статус є частиною вердикту."""

    def __init__(
        self,
        config: TesterConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self._cfg = config
        self._audit = audit or make_audit(config.audit_path)
        self._scrub: Callable[[str], str] | None = _make_redactor() if config.redact else None
        self._http = httpx.Client(
            base_url=config.base_url, timeout=config.timeout,
            auth=config.httpx_auth(), headers=config.headers(), transport=transport,
        )

    def __enter__(self) -> "GatewayHttp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> SourceResult:
        start = time.perf_counter()
        try:
            resp = self._http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            return SourceResult(0, {}, f"transport: {type(exc).__name__}", elapsed)
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            data = _as_dict(resp.json())
            error = ""
        except ValueError:
            data, error = {}, "non-json response"
        if self._scrub is not None:
            data = _as_dict(_redact_value(data, self._scrub))
        return SourceResult(resp.status_code, data, error, elapsed)


# --- Source (порт `source`) — ланцюжок ДЕКОРАТОРІВ над реальним gateway -----------

class Source:
    """Спільний інтерфейс джерела даних. Декоратори підміняють/псують відповіді, не чіпаючи бекенд."""

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        raise NotImplementedError

    def chain(self) -> list[str]:
        return [type(self).__name__]


class HttpSource(Source):
    """Реальне джерело: живий gateway client-API."""

    def __init__(self, http: GatewayHttp) -> None:
        self._http = http

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        body = request if request is not None else feature.request
        return self._http.request(feature.method, feature.path, body)


class SourceDecorator(Source):
    """База декоратора: тримає inner і делегує; підкласи підміняють поведінку вибірково."""

    def __init__(self, inner: Source) -> None:
        self._inner = inner

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        return self._inner.send(feature, request)

    def chain(self) -> list[str]:
        return [type(self).__name__, *self._inner.chain()]


class ReplaySource(SourceDecorator):
    """Підміна джерела фікстурою (sim із manifest або явною). Нема фікстури → делегат у inner."""

    def __init__(self, inner: Source, fixtures: Mapping[str, dict[str, Any]]) -> None:
        super().__init__(inner)
        self._fixtures = dict(fixtures)

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        fx = self._fixtures.get(feature.name)
        if fx is None:
            return self._inner.send(feature, request)
        try:
            status = int(fx.get("status", 200))
        except (TypeError, ValueError) as exc:
            raise ScenarioError(f"fixture status is not an int: {fx.get('status')!r}") from exc
        return SourceResult(status, _as_dict(fx.get("data")), "", 0)


class FaultSource(SourceDecorator):
    """Інʼєкція збою (бібліотека _FAULTS) для фіч із `only` (None = усі). Інші — делегат."""

    def __init__(self, inner: Source, fault: str, only: set[str] | None = None) -> None:
        super().__init__(inner)
        if fault not in _FAULTS:
            raise ScenarioError(f"unknown fault: {fault!r} (known: {', '.join(_FAULTS)})")
        self._fault = fault
        self._only = only

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        if self._only is not None and feature.name not in self._only:
            return self._inner.send(feature, request)
        if self._fault == "http_500":
            return SourceResult(500, {"detail": "injected fault"}, "", 0, injected=True)
        if self._fault == "http_404":
            return SourceResult(404, {"detail": "injected fault"}, "", 0, injected=True)
        if self._fault == "timeout":
            return SourceResult(0, {}, "transport: injected ConnectTimeout", 0, injected=True)
        if self._fault == "malformed":
            return SourceResult(200, {}, "non-json response", 0, injected=True)
        return SourceResult(200, {"reply": ""}, "", 0, injected=True)  # empty_reply

    def chain(self) -> list[str]:
        return [f"FaultSource({self._fault})", *self._inner.chain()]


class RecordingSource(SourceDecorator):
    """Passthrough + запис живих відповідей у фікстури (оновлення sim у manifest — анти-дрейф)."""

    def __init__(self, inner: Source) -> None:
        super().__init__(inner)
        self.records: dict[str, dict[str, Any]] = {}

    def send(self, feature: Feature, request: dict[str, Any] | None = None) -> SourceResult:
        result = self._inner.send(feature, request)
        if not result.error:
            self.records[feature.name] = {"status": result.status, "data": result.data}
        return result


# --- Oracle (порт `oracle`): pure-оцінка результату --------------------------------

def evaluate_feature(feature: Feature, result: SourceResult) -> dict[str, Any]:
    """SourceResult → вердикт pass|fail|skipped_gated. Anti-leak: у вердикті лише метадані."""
    oracle = feature.oracle
    reasons: list[str] = []
    status = "pass"
    if result.error:
        status, reasons = "fail", [f"transport/parse: {result.error}"]
    elif feature.gate_flag and result.status in feature.gated_statuses and not result.injected:
        # інʼєктований збій НЕ маскується під вимкнений гейт — симульований outage має бути видимим
        status, reasons = "skipped_gated", [f"фіча за прапором {feature.gate_flag} (HTTP {result.status})"]
    else:
        ok_status = [int(s) for s in (oracle.get("ok_status") or [200])]
        if result.status not in ok_status:
            reasons.append(f"HTTP {result.status}, очікував {ok_status}")
        for f in oracle.get("require_fields") or []:
            if f not in result.data:
                reasons.append(f"нема поля '{f}'")
        for f in oracle.get("nonempty_fields") or []:
            if not str(result.data.get(f) or "").strip():
                reasons.append(f"порожнє поле '{f}'")
        for f in oracle.get("forbid_fields") or []:
            if f in result.data:
                reasons.append(f"заборонене поле '{f}' присутнє (деградація)")
        budget = int(oracle.get("latency_budget_ms") or 0)
        if budget and result.elapsed_ms > budget:
            reasons.append(f"повільно: {result.elapsed_ms}ms > бюджет {budget}ms")
        if reasons:
            status = "fail"
    return {
        "feature": feature.name,
        "status": status,
        "http_status": result.status,
        "elapsed_ms": result.elapsed_ms,
        "reasons": reasons,
        "fields": sorted(result.data.keys())[:12],  # лише імена ключів — без сирих значень (anti-leak)
    }


def build_fix_task(feature: Feature, verdict: Mapping[str, Any], extra: str = "") -> str:
    """Failure-вердикт → текст задачі для coder-а. Лише метадані падіння, без сирих відповідей."""
    reasons = "; ".join(list(verdict.get("reasons") or []) or ["(причини не зафіксовані)"])
    parts = [
        f"AI_tester: фіча '{feature.name}' ({feature.title}) провалила самотест.",
        f"Ендпоінт: {feature.method} {feature.path}.",
        f"Вердикт: http={verdict.get('http_status')} за {verdict.get('elapsed_ms')}ms; причини: {reasons}.",
    ]
    if feature.on_fail_hint:
        parts.append(f"Підказка адаптера: {feature.on_fail_hint}.")
    if extra:
        parts.append(f"Додатково: {extra}.")
    parts.append("Знайди причину, поправ мінімально, прожени тести. Мутуючі кроки йдуть через confirm (S4).")
    return "\n".join(parts)


def parse_confirm_code(reply: str) -> str:
    """Код S4-підтвердження з відповіді coder/computer ('' якщо підтвердження не потрібне)."""
    m = _CONFIRM_RE.search(reply or "")
    return m.group(1) if m else ""


# --- Engine (generic оркестрація портів) -------------------------------------------

@dataclass
class _RunState:
    """Останній прогін у памʼяті процесу (report() віддає його або last_run.json з диска)."""
    report: dict[str, Any] | None = None
    seq: int = field(default=0)


class Engine:
    """Generic цикл самотестування. Нуль конкретики фіч — усе з Adapter (Open/Closed)."""

    def __init__(self, http: GatewayHttp, adapter: Adapter,
                 audit: Callable[..., None] | None = None) -> None:
        self._http = http
        self._adp = adapter
        self._audit = audit or make_audit(http._cfg.audit_path)  # noqa: SLF001 — той самий sink
        self._state = _RunState()

    # --- порт readiness: діагностика (чому тести не поїдуть) ---
    def ready(self) -> dict[str, Any]:
        out: dict[str, Any] = {"gateway": False, "profile": self._adp.profile,
                               "base_url": self._http._cfg.base_url,  # noqa: SLF001
                               "auth": "bearer" if self._http._cfg.api_key else "basic"}  # noqa: SLF001
        res = self._http.request("GET", "/api/v1/whoami")
        if res.status == 200 and not res.error:
            out["gateway"] = True
            out["identity"] = {"org_id": res.data.get("org_id"), "via": res.data.get("via")}
        else:
            out["gateway_error"] = res.error or f"HTTP {res.status}"
        feats = self._adp.features
        out["features_total"] = len(feats)
        out["features_mutating"] = sorted(n for n, f in feats.items() if f.mutating)
        out["ready"] = out["gateway"]
        return out

    # --- порт scenario: реєстр фіч ---
    def features(self) -> dict[str, Any]:
        items = [
            {"feature": f.name, "title": f.title, "endpoint": f"{f.method} {f.path}",
             "gate_flag": f.gate_flag, "mutating": f.mutating,
             "has_sim": f.sim is not None, "dispatch": f.dispatch_kind}
            for f in self._adp.features.values()
        ]
        return {"profile": self._adp.profile, "features": items}

    # --- порт source: збірка ланцюжка декораторів під режим ---
    def _build_source(self, mode: str, fault: str = "",
                      only: set[str] | None = None) -> tuple[Source, RecordingSource | None]:
        src: Source = HttpSource(self._http)
        recorder: RecordingSource | None = None
        if mode == "replay":
            fixtures = {n: f.sim for n, f in self._adp.features.items() if f.sim is not None}
            src = ReplaySource(src, fixtures)
        elif mode == "record":
            recorder = RecordingSource(src)
            src = recorder
        elif mode != "http":
            raise ScenarioError(f"unknown mode: {mode!r} (http|replay|record)")
        if fault:
            src = FaultSource(src, fault, only=only)
        return src, recorder

    # --- run: scenario → source → oracle → report ---
    def run(self, feature: str = "", mode: str = "http", fault: str = "",
            include_mutating: bool = False) -> dict[str, Any]:
        if feature:
            feats = [self._adp.feature(feature)]  # явний виклик — можна й mutating (S4 нижче)
        else:
            feats = [f for f in self._adp.features.values() if include_mutating or not f.mutating]
        src, recorder = self._build_source(mode, fault, only={feature} if feature and fault else None)
        verdicts = [evaluate_feature(f, src.send(f)) for f in feats]
        summary = {s: sum(1 for v in verdicts if v["status"] == s)
                   for s in ("pass", "fail", "skipped_gated")}
        report = {
            "run_id": self._next_run_id(),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": mode, "fault": fault, "source_chain": src.chain(),
            "requested": feature or "(suite)",
            "summary": summary, "verdicts": verdicts,
        }
        report["report_path"] = self._write_report(report)
        if recorder is not None:
            report["recorded_path"] = self._write_artifact("recordings", recorder.records)
        self._state.report = report
        self._audit("run",
                    f"run mode={mode} fault={fault or '-'} scope={feature or 'suite'} "
                    f"pass={summary['pass']} fail={summary['fail']} gated={summary['skipped_gated']}",
                    ["kind:ai_tester-run", "tool:run", f"mode:{mode}", "pillar:B"],
                    "ok" if summary["fail"] == 0 else "fail")
        return report

    # --- simulate: явна підміна джерела даних (декоратор) для однієї фічі ---
    def simulate(self, feature: str, fault: str = "", fixture_json: str = "") -> dict[str, Any]:
        feat = self._adp.feature(feature)
        fixtures: dict[str, dict[str, Any]] = {}
        if fixture_json:
            try:
                raw = json.loads(fixture_json)
            except (ValueError, TypeError) as exc:
                raise ScenarioError(f"fixture_json is not valid JSON: {exc}") from exc
            fx = _as_dict(raw)
            # Обгортка лише якщо СХОЖА на неї (int status / dict data) — інакше це тіло відповіді
            # (навіть із власним "status": "ok", як /auth/telegram/poll) → загорнемо як 200.
            is_wrapper = type(fx.get("status")) is int or isinstance(fx.get("data"), dict)
            fixtures[feature] = fx if is_wrapper else {"status": 200, "data": fx}
        elif feat.sim is not None:
            fixtures[feature] = feat.sim
        src: Source = ReplaySource(HttpSource(self._http), fixtures)
        if fault:
            src = FaultSource(src, fault, only={feature})
        substituted = bool(fault) or feature in fixtures  # чи справді була підміна джерела
        verdict = evaluate_feature(feat, src.send(feat))
        self._audit("simulate",
                    f"simulate feature={feature} fault={fault or '-'} "
                    f"fixture={'explicit' if fixture_json else ('sim' if feat.sim else 'none')} "
                    f"substituted={substituted} verdict={verdict['status']}",
                    ["kind:ai_tester-run", "tool:simulate", "pillar:B"])
        return {"verdict": verdict, "source_chain": src.chain(),
                "note": ("джерело даних підмінено декоратором — бекенд не чіпався (S2)"
                         if substituted else
                         "УВАГА: без sim-фікстури/fault підміняти нічим — запит пішов у ЖИВИЙ gateway "
                         "(дай fixture_json або fault для чистої симуляції)")}

    # --- порт dispatch: ремедіація через ті самі MCP-важелі (S4: лише дispatch) ---
    def dispatch_fix(self, feature: str, extra: str = "", target: str = "local") -> dict[str, Any]:
        feat = self._adp.feature(feature)
        verdict = self._last_verdict(feature) or {"reasons": [], "http_status": None, "elapsed_ms": None}
        task = build_fix_task(feat, verdict, extra)
        res = self._http.request("POST", "/api/v1/code/task", {"text": task, "target": target})
        reply = str(res.data.get("reply") or "")
        code = parse_confirm_code(reply)
        self._audit("dispatch_fix",
                    f"dispatch_fix feature={feature} target={target} http={res.status} "
                    f"task_chars={len(task)} awaiting_confirm={bool(code)}",
                    ["kind:ai_tester-dispatch", "tool:dispatch_fix", "pillar:B"],
                    "ok" if res.status == 200 else "fail")
        return {"feature": feature, "ok": res.status == 200 and not res.error,
                "http_status": res.status, "error": res.error, "reply": reply,
                "confirm_code": code, "awaiting_confirm": bool(code),
                "note": "S4: мутуючий крок чекає людського confirm_approve — рушій не апрувить сам"}

    def verify_ui(self, text: str) -> dict[str, Any]:
        res = self._http.request("POST", "/api/v1/driver/exec", {"text": text})
        reply = str(res.data.get("reply") or "")
        code = parse_confirm_code(reply)
        self._audit("verify_ui",
                    f"verify_ui chars_in={len(text)} http={res.status} awaiting_confirm={bool(code)}",
                    ["kind:ai_tester-dispatch", "tool:verify_ui", "pillar:B"],
                    "ok" if res.status == 200 else "fail")
        return {"ok": res.status == 200 and not res.error, "http_status": res.status,
                "error": res.error, "reply": reply,
                "confirm_code": code, "awaiting_confirm": bool(code)}

    def screenshot(self) -> dict[str, Any]:
        res = self._http.request("POST", "/api/v1/driver/screenshot", {})
        self._audit("screenshot", f"screenshot http={res.status}",
                    ["kind:ai_tester-dispatch", "tool:screenshot", "pillar:B"],
                    "ok" if res.status == 200 else "fail")
        return {"ok": res.status == 200 and not res.error,
                "http_status": res.status, "error": res.error, "text": res.data.get("text", "")}

    # --- confirm (S4) — міст до gateway; апрув завжди людський ---
    def confirm_pending(self) -> dict[str, Any]:
        data = self._http.request("GET", "/api/v1/confirm/pending").data
        self._audit("confirm_pending", f"confirm_pending pending={data.get('pending')}",
                    ["kind:ai_tester-dispatch", "tool:confirm_pending", "pillar:B"])
        return data

    def confirm_approve(self, code: str) -> dict[str, Any]:
        data = self._http.request("POST", "/api/v1/confirm/approve", {"code": code}).data
        self._audit("confirm_approve", f"confirm_approve code_len={len(code)}",
                    ["kind:ai_tester-dispatch", "tool:confirm_approve", "pillar:B"], "human-approved")
        return data

    def confirm_cancel(self) -> dict[str, Any]:
        data = self._http.request("POST", "/api/v1/confirm/cancel", {}).data
        self._audit("confirm_cancel", "confirm_cancel",
                    ["kind:ai_tester-dispatch", "tool:confirm_cancel", "pillar:B"])
        return data

    # --- луп: test → dispatch-fix → retest, bounded; зупинка на awaiting_confirm (S4) ---
    def loop_run(self, feature: str = "", max_rounds: int = 0, mode: str = "http") -> dict[str, Any]:
        if mode != "http":
            raise ScenarioError(
                f"loop_run вимагає mode='http' (дали {mode!r}): retest у replay/record не бачить фікс "
                "(фікстура статична), а dispatch бив би в живий gateway. Offline-прогін — run(mode='replay').")
        rounds = max_rounds if max_rounds > 0 else self._http._cfg.max_rounds  # noqa: SLF001
        trace: list[dict[str, Any]] = []
        last_report: dict[str, Any] | None = None
        for rnd in range(1, rounds + 1):
            last_report = self.run(feature=feature, mode=mode)
            fails = [v for v in last_report["verdicts"] if v["status"] == "fail"]
            trace.append({"round": rnd, "step": "test", "summary": last_report["summary"]})
            if not fails:
                self._audit("loop_run", f"loop_run green rounds={rnd} scope={feature or 'suite'}",
                            ["kind:ai_tester-loop", "tool:loop_run", "pillar:B"])
                return {"status": "green", "rounds": rnd, "trace": trace,
                        "report_path": last_report["report_path"]}
            target = str(fails[0]["feature"])
            feat = self._adp.feature(target)
            if feat.dispatch_kind == "computer":
                d = self.verify_ui(build_fix_task(feat, fails[0]))
            else:
                d = self.dispatch_fix(target)
            trace.append({"round": rnd, "step": f"dispatch:{feat.dispatch_kind}", "feature": target,
                          "ok": d.get("ok"), "awaiting_confirm": d.get("awaiting_confirm")})
            if d.get("awaiting_confirm"):
                self._audit("loop_run", f"loop_run awaiting_confirm feature={target} round={rnd}",
                            ["kind:ai_tester-loop", "tool:loop_run", "pillar:B"], "awaiting-confirm")
                return {"status": "awaiting_confirm", "feature": target,
                        "confirm_code": d.get("confirm_code"), "rounds": rnd, "trace": trace,
                        "note": "S4: апрувни дію людиною (confirm_approve) і повтори loop_run — "
                                "рушій ніколи не апрувить сам"}
        self._audit("loop_run", f"loop_run red rounds={rounds} scope={feature or 'suite'}",
                    ["kind:ai_tester-loop", "tool:loop_run", "pillar:B"], "fail")
        return {"status": "red", "rounds": rounds, "trace": trace,
                "report_path": (last_report or {}).get("report_path", "")}

    # --- порт report: останній прогін ---
    def report(self) -> dict[str, Any]:
        if self._state.report is not None:
            return self._state.report
        p = Path(self._http._cfg.artifacts_dir) / "last_run.json"  # noqa: SLF001
        if p.is_file():
            try:
                return _as_dict(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass
        return {"note": "ще не було жодного прогону — клич run або loop_run"}

    # --- внутрішнє: артефакти прогонів ---
    def _next_run_id(self) -> str:
        self._state.seq += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{ts}-{self._state.seq:03d}"

    def _write_report(self, report: dict[str, Any]) -> str:
        d = Path(self._http._cfg.artifacts_dir)  # noqa: SLF001
        try:
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"run-{report['run_id']}.json"
            blob = json.dumps(report, ensure_ascii=False, indent=2)
            p.write_text(blob, encoding="utf-8")
            (d / "last_run.json").write_text(blob, encoding="utf-8")
            return str(p)
        except OSError:
            return ""  # артефакт не критичний для вердикту

    def _write_artifact(self, prefix: str, payload: dict[str, Any]) -> str:
        d = Path(self._http._cfg.artifacts_dir)  # noqa: SLF001
        try:
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(p)
        except OSError:
            return ""

    def _last_verdict(self, feature: str) -> dict[str, Any] | None:
        rep = self._state.report or {}
        for v in rep.get("verdicts") or []:
            if v.get("feature") == feature:
                return dict(v)
        return None


# --- MCP server (порт `capabilities`; FastMCP лазі) --------------------------------

def build_server(engine: Engine | None = None, http: GatewayHttp | None = None) -> Any:
    """Будує FastMCP-сервер `ai_tester`. `mcp` імпортується тут (lazy, тестовність ядра)."""
    from mcp.server.fastmcp import FastMCP

    if engine is None:
        adapter = Adapter.load()
        gw = http if http is not None else GatewayHttp(TesterConfig.from_env())
        engine = Engine(gw, adapter)
    eng = engine
    server = FastMCP("ai_tester")

    def ready() -> dict[str, Any]:
        """Діагностика готовності: gateway/auth живі, скільки фіч у профілі, які mutating.
        Клич ПЕРШИМ — покаже, що підняти перед тестами (gateway :8000 / креденшели)."""
        return eng.ready()

    def features() -> dict[str, Any]:
        """Реєстр фіч профілю (adapter manifest): ендпоінт, гейт-прапор, sim-фікстура, ремедіація."""
        return eng.features()

    def run(feature: str = "", mode: str = "http", fault: str = "",
            include_mutating: bool = False) -> dict[str, Any]:
        """Прогін самотестів: feature='' = увесь suite (без mutating). mode: http (живий gateway) |
        replay (sim-фікстури, offline) | record (живий + запис фікстур). fault — інʼєкція збою.
        Звіт (метадані, без сирих відповідей) лягає в data/artifacts/ai_tester/."""
        return eng.run(feature, mode, fault, include_mutating)

    def simulate(feature: str, fault: str = "", fixture_json: str = "") -> dict[str, Any]:
        """Симуляція ендпоінта: ДЕКОРАТОР підміняє джерело даних (fixture_json / sim з manifest /
        fault: http_500|http_404|timeout|malformed|empty_reply) — бекенд не чіпається. Для
        відтворення падінь і перевірки самого oracle."""
        return eng.simulate(feature, fault, fixture_json)

    def loop_run(feature: str = "", max_rounds: int = 0, mode: str = "http") -> dict[str, Any]:
        """Автономний цикл test → dispatch-fix (coder/computer) → retest, максимум max_rounds
        (0 = AI_TESTER_MAX_ROUNDS). ЛИШЕ mode='http' (у replay фікс не видно, а dispatch живий).
        Зупиняється на awaiting_confirm: мутуючий фікс чекає ЛЮДСЬКОГО confirm_approve (S4) —
        потім повтори loop_run."""
        return eng.loop_run(feature, max_rounds, mode)

    def dispatch_fix(feature: str, extra: str = "", target: str = "local") -> dict[str, Any]:
        """Відправити coder-у задачу на фікс за останнім failure-вердиктом фічі (той самий важіль,
        що mcp__jarvis__code). S4: мутації чекають confirm_approve — ніколи не авто."""
        return eng.dispatch_fix(feature, extra, target)

    def verify_ui(text: str) -> dict[str, Any]:
        """Computer-use перевірка на реальному ПК (той самий важіль, що mcp__jarvis__computer).
        Потребує ENABLE_COMPUTER_USE; мутуючі дії → confirm-гейт (S4)."""
        return eng.verify_ui(text)

    def screenshot() -> dict[str, Any]:
        """Скріншот екрана через computer-use драйвер — швидкий доказ UI-стану для звіту."""
        return eng.screenshot()

    def report() -> dict[str, Any]:
        """Останній звіт прогону (памʼять процесу або data/artifacts/ai_tester/last_run.json)."""
        return eng.report()

    def confirm_pending() -> dict[str, Any]:
        """Чи є дія, що чекає підтвердження (S4), і її опис."""
        return eng.confirm_pending()

    def confirm_approve(code: str) -> dict[str, Any]:
        """Людський апрув дії, що очікує — за кодом із confirm_pending / loop_run (S4)."""
        return eng.confirm_approve(code)

    def confirm_cancel() -> dict[str, Any]:
        """Скасувати дію, що очікує підтвердження."""
        return eng.confirm_cancel()

    server.tool(name="ready")(ready)
    server.tool(name="features")(features)
    server.tool(name="run")(run)
    server.tool(name="simulate")(simulate)
    server.tool(name="loop_run")(loop_run)
    server.tool(name="dispatch_fix")(dispatch_fix)
    server.tool(name="verify_ui")(verify_ui)
    server.tool(name="screenshot")(screenshot)
    server.tool(name="report")(report)
    server.tool(name="confirm_pending")(confirm_pending)
    server.tool(name="confirm_approve")(confirm_approve)
    server.tool(name="confirm_cancel")(confirm_cancel)
    return server


def main() -> None:
    transport = (os.environ.get("AI_TESTER_MCP_TRANSPORT") or "stdio").strip().lower()
    server = build_server()
    if transport in ("http", "streamable-http", "streamable_http"):
        server.run(transport="streamable-http")
    elif transport == "sse":
        server.run(transport="sse")
    else:
        server.run()  # stdio


if __name__ == "__main__":
    main()
