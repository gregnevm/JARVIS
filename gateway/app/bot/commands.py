from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from ..auth import (
    agent_mode_denied_message,
    can_use_computer,
    computer_mode_denied_message,
    get_access_store,
    is_admin,
)
from ..config import settings
from ..services import ServicesClient
from ..telegram import TelegramClient
from ..tools_client import ToolsClient
from .dashboard import esc, format_dashboard, format_help
from .dispatch import CbCtx, Ctx, CallbackRegistry, CommandRegistry
from ._helpers import send_denial
from .access import handle_access_command, is_access_command
from .admin import handle_admin_command, is_admin_command
from .keyboards import (
    main_menu_keyboard,
    mode_keyboard,
    remove_reply_keyboard,
    reply_keyboard,
    reminders_hint_keyboard,
)
from .quick_actions import _run_brief, mark_keyboard_off, mark_keyboard_on, show_reply_keyboard
from .reminders_view import format_reminders_message, list_user_reminders

logger = logging.getLogger("jarvis.gateway.bot")

# Єдине джерело правди про набір slash-команд. Хендлери реєструються нижче
# декоратором `@registry.command(...)`; `is_command`, BotFather-меню
# (`bot/setup.py`) і `/help` походять із цього ж реєстру — без дублювання списків.
registry = CommandRegistry()
# Реєстр callback-кнопок (inline_keyboard) — маршрутизація за префіксом `callback_data`.
callbacks = CallbackRegistry()


def is_command(text: str) -> bool:
    if is_admin_command(text) or is_access_command(text):
        return True
    t = (text or "").strip().lower()
    if not t.startswith("/"):
        return False
    cmd = t.split()[0].split("@")[0]
    return registry.has(cmd) or cmd.startswith("/mode")


async def _present(
    tg: TelegramClient,
    chat_id: int,
    text: str,
    *,
    message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
    edit: bool = True,
) -> None:
    """Редагує inline-повідомлення або шле нове, якщо edit=False / немає message_id."""
    if edit and message_id is not None:
        await tg.edit_message_text(
            chat_id, message_id, text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await tg.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)


async def _send_dashboard(
    chat_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    *,
    user_id: int | None = None,
    message_id: int | None = None,
    edit: bool = True,
) -> None:
    dash = await svc.dashboard()
    twin = await svc.twin_status()
    body = format_dashboard(dash, twin)
    await _present(
        tg,
        chat_id,
        body,
        message_id=message_id,
        reply_markup=main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(user_id)
        ),
        edit=edit,
    )


def _mini_app_url(*, canvas: bool = False, ps: bool = False) -> str:
    url = settings.mini_app_https_url
    if not url:
        return ""
    if canvas:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}canvas=1"
    if ps:
        return f"{url}#ps"
    return url


async def _send_mini_app(
    chat_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    *,
    user_id: int | None = None,
    canvas: bool = False,
    ps: bool = False,
) -> None:
    """Відкриває Telegram Mini App — не передаємо /app агенту як шлях FS."""
    url = _mini_app_url(canvas=canvas, ps=ps)
    if url.startswith("https://"):
        if canvas:
            title = "📊 <b>Mini App — Канвас</b>"
        elif ps:
            title = "💻 <b>Mini App — PowerShell Panel</b>"
        else:
            title = "📊 <b>Mini App — JARVIS Dashboard</b>"
        await tg.send_message(
            chat_id,
            f"{title}\nНатисни кнопку нижче.",
            parse_mode="HTML",
            reply_markup={
                "inline_keyboard": [[{"text": "📊 Відкрити дашборд", "web_app": {"url": url}}]]
            },
        )
        return
    await _send_dashboard(chat_id, tg, svc, user_id=user_id, edit=False)
    lines = [
        "",
        "📱 <b>Mini App у Telegram</b> потребує <code>PUBLIC_APP_URL=https://…/app</code> "
        "(named Cloudflare tunnel — див. README).",
    ]
    if settings.webapp_dev_open:
        from ..webapp_urls import local_app_url

        local = local_app_url(settings.gateway_browser_url, canvas=canvas)
        lines.append(f"🖥 Браузер на цій машині: <code>{esc(local)}</code>")
    await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


async def _handle_project(
    raw: str, chat_id: int, user_id: int, tg: TelegramClient, redis: aioredis.Redis
) -> None:
    """`/project` — список / new <назва> / <id> (switch) / off (вийти). Активний
    проєкт скоупить RAG і додає system prompt у відповіді агента."""
    from ..projects import get_active, mem_create, mem_get, mem_list, set_active

    tokens = raw.split(maxsplit=2)
    sub = tokens[1].lower() if len(tokens) > 1 else "list"

    if sub in ("off", "clear", "exit", "none"):
        await set_active(redis, user_id, None)
        await tg.send_message(chat_id, "📁 Вийшов із проєкту — загальний контекст.")
        return

    if sub in ("new", "create", "+"):
        name = tokens[2].strip() if len(tokens) > 2 else ""
        if not name:
            await tg.send_message(
                chat_id, "Вкажи назву: <code>/project new Робота</code>", parse_mode="HTML"
            )
            return
        proj = await mem_create(user_id, name)
        if not proj:
            await tg.send_message(chat_id, "Не вдалося створити проєкт.")
            return
        await set_active(redis, user_id, int(proj["id"]))
        await tg.send_message(
            chat_id,
            f"✅ Проєкт «{esc(proj['name'])}» #{proj['id']} створено й активовано.",
            parse_mode="HTML",
        )
        return

    target: int | None = None
    if sub == "switch" and len(tokens) > 2 and tokens[2].strip().isdigit():
        target = int(tokens[2].strip())
    elif sub.isdigit():
        target = int(sub)
    if target is not None:
        proj = await mem_get(user_id, target)
        if not proj:
            await tg.send_message(chat_id, "Проєкт не знайдено.")
            return
        await set_active(redis, user_id, target)
        await tg.send_message(
            chat_id, f"📁 Активний проєкт: «{esc(proj['name'])}» #{target}.", parse_mode="HTML"
        )
        return

    projects = await mem_list(user_id)
    active = await get_active(redis, user_id)
    if not projects:
        await tg.send_message(
            chat_id,
            "Проєктів ще немає. Створи: <code>/project new Назва</code>",
            parse_mode="HTML",
        )
        return
    lines = ["📁 <b>Твої проєкти</b>"]
    for p in projects:
        mark = " ✅" if p["id"] == active else ""
        lines.append(f"#{p['id']} {esc(p['name'])}{mark}")
    lines.append(
        "\nПеремкнути: <code>/project &lt;id&gt;</code> · "
        "Новий: <code>/project new Назва</code> · Вийти: <code>/project off</code>"
    )
    await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


# --------------------------------------------------------------------------- #
# Зареєстровані хендлери команд. Кожен бере `Ctx`; повертає True (команду спожито).
# Метадані (`description`, `menu`, `admin`) живуть тут же → BotFather-меню і /help
# не дублюють список. Раніше `/login`, `/plan`, `/improve` випадали з `COMMANDS`
# і ставали недосяжними — реєстр прибирає цей клас помилок (один список).
# --------------------------------------------------------------------------- #


_TGAUTH_TTL = 300


async def bind_tgauth_login(redis: aioredis.Redis, token: str, user_id: int) -> bool:
    """Прив'язати *pending* токен Telegram-логіну до telegram_id користувача (single-use).

    Армується лише токен, який клієнт створив через ``POST /auth/telegram/start`` (значення
    ``"pending"``). Це відкидає: токен, якого сервер не мінтив (attacker-chosen deeplink →
    session-fixation), токен, уже спожитий ``/poll`` (resurrection), і токен, уже прив'язаний до
    іншого uid (clobber — first-confirm-wins). Перевірка-потім-запис безпечна без транзакції:
    не-``"pending"`` значення відкидається за будь-якого чергування, тож жоден arm не звертає
    непричетний токен на нового uid; єдина гонка — між двома одночасними підтвердженнями того
    самого вже-pending секретного токена, що не є межею привілеїв. (Прив'язку poll-каналу до
    клієнта, що мінтив, тут не вирішуємо — це окремий шар.)
    """
    key = f"tgauth:{token}"
    if await redis.get(key) != "pending":
        return False
    await redis.setex(key, _TGAUTH_TTL, str(user_id))
    return True


@registry.command("/start", description="Головне меню", menu=True)
async def _cmd_start(ctx: Ctx) -> bool:
    raw_payload = ctx.args
    payload = raw_payload.lower()
    # Telegram-логін мобільного застосунку: APK відкриває t.me/<bot>?start=tgauth_<token>,
    # тут прив'язуємо token → telegram_id (case-sensitive токен з raw_payload). APK потім
    # обмінює token на JWT через /api/v1/auth/telegram/poll.
    if payload.startswith("tgauth_") and ctx.redis is not None:
        token = raw_payload[len("tgauth_"):]
        if token and await bind_tgauth_login(ctx.redis, token, ctx.user_id):
            await ctx.tg.send_message(
                ctx.chat_id, "✅ Вхід у застосунок JARVIS підтверджено — повертайся в додаток."
            )
        else:
            await ctx.tg.send_message(
                ctx.chat_id,
                "🔴 Це посилання для входу недійсне або застаріле. "
                "Відкрий застосунок JARVIS і почни вхід знову.",
            )
        return True
    if payload == "app":
        await _send_mini_app(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id)
        return True
    if payload in ("connect", "login"):
        from .auth_link import send_connect_menu

        await send_connect_menu(ctx.chat_id, ctx.tg)
        return True
    if payload.startswith("mode_"):
        mode = payload[5:]
        denied = agent_mode_denied_message(ctx.user_id) or computer_mode_denied_message(
            ctx.user_id, mode
        )
        if await send_denial(ctx.tg, ctx.chat_id, denied):
            return True
        res = await ctx.svc.set_mode(mode)
        if res.get("error"):
            await ctx.tg.send_message(ctx.chat_id, f"🔴 {esc(res['error'])}")
        else:
            await ctx.tg.send_message(
                ctx.chat_id,
                f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>",
                parse_mode="HTML",
                reply_markup=mode_keyboard(show_computer=can_use_computer(ctx.user_id)),
            )
        return True
    if payload in ("remind", "reminders"):
        await ctx.tg.send_message(
            ctx.chat_id,
            "⏰ Нагадування: напиши «нагадай через 30 хв …» або /reminders",
        )
        return True
    if payload == "canvas":
        await _send_mini_app(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id, canvas=True)
        return True
    await _send_dashboard(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id, edit=False)
    return True


@registry.command("/dashboard", description="Панель + inline-кнопки", menu=True)
async def _cmd_dashboard(ctx: Ctx) -> bool:
    await _send_dashboard(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id, edit=False)
    return True


@registry.command("/app", description="Mini App дашборд (HTTPS)", menu=True)
async def _cmd_app(ctx: Ctx) -> bool:
    await _send_mini_app(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id, ps=True)
    return True


@registry.command(
    "/connect",
    description="Підключити веб-консоль / застосунок / розширення",
    menu=True,
    aliases=("/pair",),
)
async def _cmd_connect(ctx: Ctx) -> bool:
    """Хаб авторизації інших ендпоінтів через Telegram (один тап)."""
    from .auth_link import handle_connect_callback, send_connect_menu

    arg = ctx.args.lower()
    # Прямі канали: `/connect web|app|ext` оминають меню (redis-None обробляється всередині).
    if arg in ("web", "app", "ext"):
        return await handle_connect_callback(
            f"conn:{arg}", ctx.chat_id, ctx.user_id, ctx.tg, ctx.redis
        )
    await send_connect_menu(ctx.chat_id, ctx.tg)
    return True


@registry.command("/login", description="Швидкий вхід у застосунок")
async def _cmd_login(ctx: Ctx) -> bool:
    if ctx.redis is None:
        await ctx.tg.send_message(ctx.chat_id, "Логін недоступний (redis off).")
        return True
    from .auth_link import send_app_login

    await send_app_login(ctx.chat_id, ctx.user_id, ctx.tg, ctx.redis)
    return True


@registry.command("/help", description="Довідка", menu=True)
async def _cmd_help(ctx: Ctx) -> bool:
    await ctx.tg.send_message(
        ctx.chat_id,
        format_help(),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(ctx.user_id)
        ),
    )
    return True


@registry.command("/status", description="Стан Ollama / Twin", menu=True)
async def _cmd_status(ctx: Ctx) -> bool:
    await _send_dashboard(ctx.chat_id, ctx.tg, ctx.svc, user_id=ctx.user_id, edit=False)
    return True


@registry.command("/sync", description="Twin ingest + LoRA", menu=True)
async def _cmd_sync(ctx: Ctx) -> bool:
    twin = await ctx.svc.twin_status()
    if not twin:
        await ctx.tg.send_message(ctx.chat_id, "🔴 Twin недоступний (перевір сервіс twin:8765).")
        return True
    await ctx.tg.send_message(
        ctx.chat_id,
        format_dashboard({}, twin),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(ctx.user_id)
        ),
    )
    return True


@registry.command("/brief", description="Короткий бриф", menu=True)
async def _cmd_brief(ctx: Ctx) -> bool:
    if ctx.tools is None:
        await ctx.tg.send_message(ctx.chat_id, "Агент недоступний.")
        return True
    await _run_brief(ctx.chat_id, ctx.user_id, ctx.tg, ctx.svc, ctx.tools, ctx.redis)
    return True


@registry.command("/dataset", description="Експорт датасету (admin)", admin=True)
async def _cmd_dataset(ctx: Ctx) -> bool:
    if not is_admin(ctx.user_id):
        await ctx.tg.send_message(ctx.chat_id, "⛔ Лише для адмінів (ADMIN_USER_IDS).")
        return True
    if ctx.tools is None:
        await ctx.tg.send_message(ctx.chat_id, "Tools недоступний.")
        return True
    stats = await ctx.tools.dataset_stats(int(ctx.user_id))
    info = await ctx.tools.export_dataset(int(ctx.user_id))
    if info.get("error"):
        await ctx.tg.send_message(ctx.chat_id, f"Експорт не вдався: {info['error']}")
        return True
    sched = info.get("scheduler") or stats
    ready = "✅" if sched.get("retrain_ready") else "—"
    await ctx.tg.send_message(
        ctx.chat_id,
        "📦 Dataset export\n"
        f"curated: {stats.get('curated_turns', '?')} · files: {stats.get('files', '?')}\n"
        f"train: {info.get('train', 0)} · holdout: {info.get('holdout', 0)}\n"
        f"retrain +{sched.get('curated_since_export', '?')}/{sched.get('retrain_threshold', '?')} {ready}\n"
        f"<code>{info.get('train_path', '')}</code>",
        parse_mode="HTML",
    )
    return True


@registry.command("/improve", description="Self-improve (admin)", admin=True)
async def _cmd_improve(ctx: Ctx) -> bool:
    if not is_admin(ctx.user_id):
        await ctx.tg.send_message(ctx.chat_id, "⛔ Лише для адмінів (ADMIN_USER_IDS).")
        return True
    if ctx.tools is None:
        await ctx.tg.send_message(ctx.chat_id, "Tools недоступний.")
        return True
    sub = (ctx.arg_list[0] if ctx.arg_list else "status").strip()
    if sub == "scan":
        out = await ctx.tools.improve_scan(int(ctx.user_id))
        if out.get("error"):
            await ctx.tg.send_message(ctx.chat_id, f"Scan failed: {out['error']}")
            return True
        await ctx.tg.send_message(
            ctx.chat_id,
            "🔄 Improve scan\n"
            f"scanned: {out.get('scanned', 0)} · queued: {out.get('queued', 0)} · "
            f"rejected: {out.get('rejected', 0)}\n"
            f"pending total: {out.get('pending_total', 0)}",
        )
        return True
    st = await ctx.tools.improve_status(int(ctx.user_id))
    rt = st.get("retrain") or {}
    await ctx.tg.send_message(
        ctx.chat_id,
        "📈 Self-improve\n"
        f"pending: {st.get('pending', 0)} · approved: {st.get('approved_total', 0)}\n"
        f"retrain +{rt.get('curated_since_export', '?')}/{rt.get('retrain_threshold', '?')} "
        f"{'✅' if rt.get('retrain_ready') else '—'}\n"
        "Команди: /improve scan",
    )
    return True


@registry.command("/project", description="Проєкти: list / new / switch / off", menu=True)
async def _cmd_project(ctx: Ctx) -> bool:
    if ctx.redis is None:
        await ctx.tg.send_message(ctx.chat_id, "Проєкти недоступні (Redis).")
        return True
    await _handle_project(ctx.raw, ctx.chat_id, ctx.user_id, ctx.tg, ctx.redis)
    return True


@registry.command("/plan", description="План із підтвердженням")
async def _cmd_plan(ctx: Ctx) -> bool:
    if ctx.tools is None:
        await ctx.tg.send_message(ctx.chat_id, "Tools недоступний.")
        return True
    from .plans import send_plan_confirm

    plan_parts = ctx.raw.split(maxsplit=2)
    if len(plan_parts) >= 3 and plan_parts[1].lower() == "execute":
        plan_id = plan_parts[2].strip()
        await ctx.tg.send_message(
            ctx.chat_id, f"⏳ Виконую план <code>{esc(plan_id)}</code>…", parse_mode="HTML"
        )
        result = await ctx.tools.execute_plan(plan_id, ctx.user_id)
        if result.get("error"):
            await ctx.tg.send_message(
                ctx.chat_id, f"🔴 {esc(str(result['error']))}", parse_mode="HTML"
            )
        else:
            text = str(result.get("result") or "")[:3500]
            await ctx.tg.send_message(ctx.chat_id, text or "План виконано ✅")
        return True
    task = ctx.args
    if not task:
        await ctx.tg.send_message(
            ctx.chat_id,
            "📋 <code>/plan &lt;задача&gt;</code> — створити план\n"
            "<code>/plan execute &lt;id&gt;</code> — виконати схвалений план",
            parse_mode="HTML",
        )
        return True
    plan = await ctx.tools.create_plan(ctx.user_id, task)
    if plan.get("error"):
        await ctx.tg.send_message(ctx.chat_id, f"🔴 {esc(str(plan['error']))}")
        return True
    await send_plan_confirm(
        ctx.chat_id, str(plan.get("id") or ""), str(plan.get("summary") or task), ctx.tg
    )
    return True


@registry.command("/apk", description="MVP Android-клієнт (.apk)")
async def _cmd_apk(ctx: Ctx) -> bool:
    from .apk import handle_apk_command

    return await handle_apk_command(ctx.chat_id, ctx.user_id, ctx.tg, redis=ctx.redis)


@registry.command("/cursor", description="Cursor IDE (admin)", admin=True)
async def _cmd_cursor(ctx: Ctx) -> bool:
    if ctx.tools is None:
        await ctx.tg.send_message(ctx.chat_id, "Tools недоступний.")
        return True
    from .cursor_flow import handle_cursor_command

    return await handle_cursor_command(ctx.raw, ctx.chat_id, ctx.user_id, ctx.tg, ctx.tools, ctx.redis)


@registry.command("/reminders", description="Активні нагадування", menu=True)
async def _cmd_reminders(ctx: Ctx) -> bool:
    if ctx.redis is None:
        await ctx.tg.send_message(ctx.chat_id, "Redis недоступний.")
        return True
    sub = (ctx.arg_list[0] if ctx.arg_list else "")
    if sub == "ics":
        if ctx.tools is None:
            await ctx.tg.send_message(ctx.chat_id, "Tools недоступний.")
            return True
        ics = await ctx.tools.reminders_ics(ctx.user_id)
        if not ics:
            await ctx.tg.send_message(
                ctx.chat_id,
                "Немає активних нагадувань для експорту. /reminders ics — після set_reminder.",
            )
            return True
        await ctx.tg.send_document(
            ctx.chat_id, ics, filename="jarvis-reminders.ics", caption="📅 Експорт нагадувань"
        )
        return True
    body = await list_user_reminders(ctx.redis, ctx.user_id)
    await ctx.tg.send_message(
        ctx.chat_id,
        format_reminders_message(body) + "\n\n📅 Експорт: <code>/reminders ics</code>",
        parse_mode="HTML",
        reply_markup=reminders_hint_keyboard(),
    )
    return True


@registry.command("/keyboard", description="Показати або сховати кнопки", menu=True)
async def _cmd_keyboard(ctx: Ctx) -> bool:
    sub = ctx.arg_list[0] if ctx.arg_list else "on"
    if sub in ("off", "hide", "сховати"):
        if ctx.redis is not None:
            await mark_keyboard_off(ctx.redis, ctx.user_id)
        await ctx.tg.send_message(
            ctx.chat_id,
            "⌨️ Клавіатуру приховано. /keyboard on — показати знову.",
            reply_markup=remove_reply_keyboard(),
        )
    elif settings.telegram_reply_keyboard:
        await show_reply_keyboard(ctx.tg, ctx.chat_id, ctx.redis, ctx.user_id)
    else:
        await ctx.tg.send_message(
            ctx.chat_id,
            "Reply Keyboard вимкнено (TELEGRAM_REPLY_KEYBOARD=false).",
        )
    return True


@registry.command("/mode", description="Режим chat/agent/hybrid/computer", menu=True)
async def _cmd_mode(ctx: Ctx) -> bool:
    args = ctx.arg_list
    denied = agent_mode_denied_message(ctx.user_id)
    if denied and len(args) >= 1:
        await ctx.tg.send_message(ctx.chat_id, denied)
        return True
    if len(args) >= 1:
        mode = args[0]
        denied = computer_mode_denied_message(ctx.user_id, mode)
        if await send_denial(ctx.tg, ctx.chat_id, denied):
            return True
        res = await ctx.svc.set_mode(mode)
        if res.get("error"):
            await ctx.tg.send_message(
                ctx.chat_id, f"🔴 Не вдалося змінити режим: {esc(res['error'])}"
            )
        else:
            await ctx.tg.send_message(
                ctx.chat_id,
                f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>",
                parse_mode="HTML",
                reply_markup=mode_keyboard(show_computer=can_use_computer(ctx.user_id)),
            )
        return True
    dash = await ctx.svc.dashboard()
    cur = dash.get("agent_mode", "?")
    await ctx.tg.send_message(
        ctx.chat_id,
        f"🧠 Поточний режим: <code>{esc(cur)}</code>\n"
        "Обери кнопкою або: <code>/mode chat|agent|hybrid|computer</code>",
        parse_mode="HTML",
        reply_markup=mode_keyboard(show_computer=can_use_computer(ctx.user_id)),
    )
    return True


async def handle_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    redis: aioredis.Redis | None = None,
    tools: ToolsClient | None = None,
    *,
    message: dict[str, Any] | None = None,
) -> bool:
    """Тонкий диспетчер: access/admin делегуються, решта — через реєстр команд.

    True — команду спожито (агент далі НЕ викликається)."""
    store = get_access_store()
    if is_access_command(text) and store is not None:
        return await handle_access_command(
            text, chat_id, user_id, tg, store, message=message
        )

    if is_admin_command(text) and redis is not None:
        return await handle_admin_command(text, chat_id, user_id, tg, svc, redis)

    ctx = Ctx(
        text=text or "",
        chat_id=chat_id,
        user_id=user_id,
        tg=tg,
        svc=svc,
        redis=redis,
        tools=tools,
        message=message,
    )
    spec = registry.get(ctx.cmd)
    if spec is None:
        return False
    return await spec.handler(ctx)


# --------------------------------------------------------------------------- #
# Callback-хендлери (inline-кнопки). Кожен бере `CbCtx`, повертає True (спожито).
# Делеговані (conn/acc/adm/pln/cmp/agt) — тонкі адаптери до підмодулів; решта
# (mode/dash) — локальна dashboard-навігація. Раніше — ладдер `if data.startswith`.
# --------------------------------------------------------------------------- #


@callbacks.callback("conn:")
async def _cb_conn(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    from .auth_link import handle_connect_callback

    await cb.ack("Готую посилання…")
    return await handle_connect_callback(
        cb.data, cb.chat_id, int(cb.user_id), cb.tg, cb.redis
    )


@callbacks.callback("acc:")
async def _cb_acc(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    store = get_access_store()
    if store is None:
        return False
    from .access import handle_access_callback

    await cb.ack()
    return await handle_access_callback(cb.data, cb.chat_id, int(cb.user_id), cb.tg, store)


@callbacks.callback("adm:", needs_redis=True)
async def _cb_adm(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    assert cb.redis is not None  # гарантовано needs_redis
    from .admin import handle_admin_callback

    await cb.ack()
    return await handle_admin_callback(
        cb.data, cb.chat_id, int(cb.user_id), cb.tg, cb.svc, cb.redis
    )


@callbacks.callback("pln:", needs_tools=True)
async def _cb_pln(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    assert cb.tools is not None  # гарантовано needs_tools
    from .plans import handle_plan_callback

    await cb.ack()
    return await handle_plan_callback(cb.data, cb.chat_id, int(cb.user_id), cb.tg, cb.tools)


@callbacks.callback("cmp:", needs_tools=True)
async def _cb_cmp(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    assert cb.tools is not None  # гарантовано needs_tools
    from .computer import handle_computer_callback

    await cb.ack()
    return await handle_computer_callback(
        cb.data, cb.chat_id, int(cb.user_id), cb.tg, cb.tools, redis=cb.redis
    )


@callbacks.callback("agt:", needs_tools=True)
async def _cb_agt(cb: CbCtx) -> bool:
    if cb.user_id is None:
        return False
    assert cb.tools is not None  # гарантовано needs_tools
    from ..agent_turn import run_agent_turn

    await cb.ack("Обробляю…")
    await run_agent_turn(
        cb.tg,
        cb.tools,
        cb.chat_id,
        {
            "user_id": int(cb.user_id),
            "chat_id": cb.chat_id,
            "text": f"Користувач натиснув кнопку ({cb.data}). Відреагуй коротко.",
            "type": "callback",
            "mode": "auto",
        },
        redis=cb.redis,
        user_id=int(cb.user_id),
    )
    return True


@callbacks.callback("mode:")
async def _cb_mode(cb: CbCtx) -> bool:
    mode = cb.data.split(":", 1)[1]
    denied = agent_mode_denied_message(cb.user_id) or computer_mode_denied_message(
        cb.user_id, mode
    )
    if denied:
        await cb.ack(denied[:200])
        await cb.tg.send_message(cb.chat_id, denied)
        return True
    res = await cb.svc.set_mode(mode)
    if res.get("error"):
        toast = f"Помилка: {res['error'][:180]}"
        text = f"🔴 {esc(res['error'])}"
    else:
        mode_name = str(res.get("mode", mode))
        toast = f"Режим: {mode_name}"
        text = f"🧠 Режим: <code>{esc(mode_name)}</code>"
    await _present(
        cb.tg,
        cb.chat_id,
        text,
        message_id=cb.message_id,
        reply_markup=mode_keyboard(show_computer=can_use_computer(cb.user_id)),
    )
    await cb.ack(toast)
    return True


@callbacks.callback("dash:")
async def _cb_dash(cb: CbCtx) -> bool:
    """Dashboard-навігація: menu / help / brief / reminders / status / sync / mode."""
    data = cb.data
    if data == "dash:brief":
        if cb.tools is not None and cb.user_id is not None:
            await cb.ack("Готую бриф…")
            await _run_brief(cb.chat_id, int(cb.user_id), cb.tg, cb.svc, cb.tools, cb.redis)
        else:
            await cb.ack()
        return True
    if data == "dash:reminders":
        if cb.redis is not None:
            body = await list_user_reminders(cb.redis, int(cb.user_id or 0))
            await _present(
                cb.tg,
                cb.chat_id,
                format_reminders_message(body),
                message_id=cb.message_id,
                reply_markup=reminders_hint_keyboard(),
            )
        await cb.ack()
        return True
    if data == "dash:help":
        await _present(
            cb.tg,
            cb.chat_id,
            format_help(),
            message_id=cb.message_id,
            reply_markup=main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(cb.user_id)
            ),
        )
        await cb.ack()
        return True
    # dash:menu | dash:status | dash:sync | dash:mode → панель/режим
    dash = await cb.svc.dashboard()
    twin = await cb.svc.twin_status()
    if data == "dash:mode":
        text = f"🧠 Режим: <code>{esc(dash.get('agent_mode', '?'))}</code>"
        markup = mode_keyboard(show_computer=can_use_computer(cb.user_id))
    elif data == "dash:sync":
        text = format_dashboard({}, twin) if twin else "🔴 Twin недоступний."
        markup = main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(cb.user_id)
        )
    else:  # dash:menu | dash:status
        text = format_dashboard(dash, twin)
        markup = main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(cb.user_id)
        )
    await _present(cb.tg, cb.chat_id, text, message_id=cb.message_id, reply_markup=markup)
    await cb.ack()
    return True


async def handle_callback(
    callback: dict[str, Any],
    tg: TelegramClient,
    svc: ServicesClient,
    redis: Any = None,
    tools: Any = None,
) -> None:
    """Тонкий диспетчер callback_query: класифікує `data` за префіксом → реєстр."""
    data = str(callback.get("data") or "")
    msg = callback.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    user_id = (callback.get("from") or {}).get("id")
    if chat_id is None:
        return

    message_id = msg.get("message_id")
    cb = CbCtx(
        data=data,
        chat_id=int(chat_id),
        user_id=int(user_id) if user_id is not None else None,
        message_id=int(message_id) if message_id is not None else None,
        cq_id=str(callback["id"]) if callback.get("id") else None,
        tg=tg,
        svc=svc,
        redis=redis,
        tools=tools,
    )
    if await callbacks.dispatch(cb):
        return
    # нічого не спожило (невідома кнопка / не виконано guard) → прибрати «годинник»
    await cb.ack()
