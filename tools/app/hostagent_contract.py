"""Контракт API host-agent ↔ tools/computer.py (Фаза 5.1)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HostagentRoute:
    method: Literal["GET", "POST"]
    path: str
    json_body: bool = False
    query_params: bool = False


# Маршрути, які викликає tools/app/computer.py (і bootstrap /health).
TOOLS_HOSTAGENT_ROUTES: tuple[HostagentRoute, ...] = (
    HostagentRoute("GET", "/health"),
    HostagentRoute("GET", "/health/stack"),
    HostagentRoute("POST", "/powershell", json_body=True),
    HostagentRoute("POST", "/cli", json_body=True),
    HostagentRoute("GET", "/fs/list", query_params=True),
    HostagentRoute("GET", "/fs/read", query_params=True),
    HostagentRoute("GET", "/fs/download", query_params=True),
    HostagentRoute("POST", "/fs/write", json_body=True),
    HostagentRoute("POST", "/fs/write_bytes", json_body=True),
    HostagentRoute("POST", "/screen/capture"),
    HostagentRoute("POST", "/screen/click", json_body=True),
    HostagentRoute("POST", "/screen/type", json_body=True),
    HostagentRoute("POST", "/screen/hotkey", json_body=True),
    HostagentRoute("POST", "/screen/scroll", json_body=True),
    HostagentRoute("GET", "/clipboard"),
    HostagentRoute("POST", "/clipboard", json_body=True),
    HostagentRoute("GET", "/window/list"),
    HostagentRoute("POST", "/window/focus", query_params=True),
    HostagentRoute("POST", "/uia/invoke", json_body=True),
    HostagentRoute("POST", "/power", json_body=True),
)

# Шляхи, що мають зустрічатися в computer.py (регресія при перейменуванні).
COMPUTER_SOURCE_PATHS: frozenset[str] = frozenset(
    r.path for r in TOOLS_HOSTAGENT_ROUTES if r.path not in ("/health", "/health/stack")
)
