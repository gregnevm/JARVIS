"""Settings-блоки і env-інвентар (R4 «Тонкий шлюз», P7 SSOT + D1 машиною)."""
from .blocks import (
    AuthIdsCfg,
    ComputerCfg,
    CoreServiceUrls,
    DataDirCfg,
    OllamaCfg,
    RedisCfg,
)
from .inventory import settings_inventory

__all__ = [
    "AuthIdsCfg",
    "ComputerCfg",
    "CoreServiceUrls",
    "DataDirCfg",
    "OllamaCfg",
    "RedisCfg",
    "settings_inventory",
]
