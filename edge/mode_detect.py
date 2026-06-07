"""Mode-detect OFFLINE / LAN / VPN (DESIGN §3.2)."""
from __future__ import annotations

import socket
from typing import Literal
from urllib.parse import urlparse

ConnectMode = Literal["OFFLINE", "LAN", "VPN"]


def _host_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.hostname or "127.0.0.1"


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_mode(
    twin_url: str,
    *,
    vpn_hosts: tuple[str, ...] = (),
    timeout: float = 2.0,
) -> ConnectMode:
    """OFFLINE — Twin недоступний; LAN/VPN — Twin health OK (VPN за списком host)."""
    if not twin_url.strip():
        return "OFFLINE"
    host = _host_from_url(twin_url)
    port = urlparse(twin_url if "://" in twin_url else f"http://{twin_url}").port or 8765
    if not _tcp_reachable(host, port, timeout=timeout):
        return "OFFLINE"
    if vpn_hosts and host in vpn_hosts:
        return "VPN"
    return "LAN"
