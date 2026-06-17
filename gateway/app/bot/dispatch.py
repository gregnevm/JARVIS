"""Реєстр команд і callback-ів Telegram-бота — єдина точка маршрутизації.

Замість двох гігантських if/elif (`handle_command` / `handle_callback`) — декларативні
реєстри. Команда реєструється один раз; із того самого реєстру походять `is_command`,
BotFather-меню (`bot/setup.py`) та `/help` (`bot/dashboard.py`). Жодного дублювання
списку команд — раніше `COMMANDS` розходився з реальними хендлерами, через що
`/login`, `/plan`, `/improve` ставали недосяжними (`is_command` повертав False).

Архітектура (P3/P4 — композиція замість моноліту):
  * `Ctx`              — усе, що потрібно хендлеру; транспорт уже розібрано роутером.
  * `CommandRegistry`  — `/cmd` → `CommandSpec` (хендлер + метадані для меню/довідки).
  * `CallbackRegistry` — префікс callback_data (`"mode:"`, `"dash:"`, …) → хендлер.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis

from ..services import ServicesClient
from ..telegram import TelegramClient
from ..tools_client import ToolsClient


@dataclass
class Ctx:
    """Контекст виконання команди. Роутер уже зробив auth + rate-limit + ingest."""

    text: str
    chat_id: int
    user_id: int
    tg: TelegramClient
    svc: ServicesClient
    redis: aioredis.Redis | None = None
    tools: ToolsClient | None = None
    message: dict[str, Any] | None = None

    @property
    def raw(self) -> str:
        return (self.text or "").strip()

    @property
    def parts(self) -> list[str]:
        return self.raw.split()

    @property
    def cmd(self) -> str:
        """Нормалізована команда: `/Mode@Bot agent` → `/mode`."""
        p = self.parts
        return p[0].split("@")[0].lower() if p else ""

    @property
    def args(self) -> str:
        """Усе після команди одним рядком (case-збережено): `/project new Робота` → `new Робота`."""
        sp = self.raw.split(maxsplit=1)
        return sp[1].strip() if len(sp) > 1 else ""

    @property
    def arg_list(self) -> list[str]:
        """Аргументи (нижній регістр, як у старому `parts[1:]`)."""
        return self.raw.lower().split()[1:]


# Хендлер повертає True, якщо команду спожито (агент далі НЕ викликається).
CommandHandler = Callable[[Ctx], Awaitable[bool]]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: CommandHandler
    description: str = ""
    menu: bool = False           # показувати у BotFather-меню (setMyCommands)
    admin: bool = False          # лише для адмінів (групування у /help)
    aliases: tuple[str, ...] = ()


class CommandRegistry:
    """Декларативний реєстр slash-команд. Єдине джерело правди про набір команд."""

    def __init__(self) -> None:
        self._by_name: dict[str, CommandSpec] = {}
        self._order: list[CommandSpec] = []

    def add(self, spec: CommandSpec) -> CommandSpec:
        if spec not in self._order:
            self._order.append(spec)
        for name in (spec.name, *spec.aliases):
            self._by_name[name] = spec
        return spec

    def command(
        self,
        name: str,
        *,
        description: str = "",
        menu: bool = False,
        admin: bool = False,
        aliases: tuple[str, ...] = (),
    ) -> Callable[[CommandHandler], CommandHandler]:
        """Декоратор реєстрації: `@registry.command("/login", description=…, menu=True)`."""

        def deco(fn: CommandHandler) -> CommandHandler:
            self.add(
                CommandSpec(
                    name=name,
                    handler=fn,
                    description=description,
                    menu=menu,
                    admin=admin,
                    aliases=aliases,
                )
            )
            return fn

        return deco

    def get(self, cmd: str) -> CommandSpec | None:
        return self._by_name.get(cmd)

    def has(self, cmd: str) -> bool:
        return cmd in self._by_name

    def specs(self) -> list[CommandSpec]:
        """Усі spec-и у порядку реєстрації (без дублів-аліасів)."""
        return list(self._order)

    def menu_commands(self) -> list[dict[str, str]]:
        """Список для `setMyCommands` (BotFather-меню) — лише `menu=True`."""
        return [
            {"command": s.name.lstrip("/"), "description": s.description}
            for s in self._order
            if s.menu
        ]


# Callback-маршрутизація за префіксом `callback_data` (будуються в keyboards.py).
@dataclass
class CbCtx:
    """Контекст callback_query. Транспорт (chat/message/user) уже розібрано роутером."""

    data: str
    chat_id: int
    user_id: int | None
    message_id: int | None
    cq_id: str | None
    tg: TelegramClient
    svc: ServicesClient
    redis: aioredis.Redis | None = None
    tools: ToolsClient | None = None

    async def ack(self, text: str | None = None) -> None:
        """answer_callback_query (прибирає «годинник» на кнопці). No-op без cq_id."""
        if self.cq_id:
            await self.tg.answer_callback_query(str(self.cq_id), text=text)


# Хендлер повертає True, якщо callback спожито (інакше — фінальний ack у диспетчері).
CallbackHandler = Callable[[CbCtx], Awaitable[bool]]


@dataclass(frozen=True)
class CallbackSpec:
    prefix: str
    handler: CallbackHandler
    needs_tools: bool = False    # пропустити (→ фінальний ack), якщо tools відсутній
    needs_redis: bool = False    # пропустити (→ фінальний ack), якщо redis відсутній


class CallbackRegistry:
    """Реєстр callback-хендлерів за префіксом `data` (довший префікс виграє першим)."""

    def __init__(self) -> None:
        self._specs: list[CallbackSpec] = []

    def add(self, spec: CallbackSpec) -> None:
        self._specs.append(spec)
        # довші префікси — раніше, щоб напр. "cmpA:" не перехоплювався "cmp:"
        self._specs.sort(key=lambda s: len(s.prefix), reverse=True)

    def callback(
        self, prefix: str, *, needs_tools: bool = False, needs_redis: bool = False
    ) -> Callable[[CallbackHandler], CallbackHandler]:
        def deco(fn: CallbackHandler) -> CallbackHandler:
            self.add(CallbackSpec(prefix, fn, needs_tools, needs_redis))
            return fn

        return deco

    def match(self, data: str) -> CallbackSpec | None:
        for spec in self._specs:
            if data.startswith(spec.prefix):
                return spec
        return None

    async def dispatch(self, cb: CbCtx) -> bool:
        """Знаходить хендлер за префіксом, перевіряє guard-и, викликає. True — спожито."""
        spec = self.match(cb.data)
        if spec is None:
            return False
        if spec.needs_tools and cb.tools is None:
            return False
        if spec.needs_redis and cb.redis is None:
            return False
        return await spec.handler(cb)
