import asyncio
import html
import logging
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from .amounts import minor_to_text
from .config import Settings
from .repository import DeltaRepository
from .telegram_auth import TelegramUser

logger = logging.getLogger(__name__)
# NOVERA partner statistics command + notification entry point

_PLACEHOLDER_LINK_MARKERS = (
    "your_support",
    "your_chat",
    "example.com",
    "t.me/your_",
)


def _webapp_url(
    base: str,
    *,
    view: str | None = None,
    tab: str | None = None,
    login_token: str | None = None,
) -> str:
    params = {}
    if view:
        params["view"] = view
    if tab:
        params["tab"] = tab
    if login_token:
        params["login"] = login_token
    if not params:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode(params)}"


def _is_public_link(url: str | None) -> bool:
    if not url:
        return False
    candidate = url.strip()
    if not candidate.startswith(("https://", "http://", "tg://")):
        return False
    lowered = candidate.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_LINK_MARKERS)


def _html_link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _build_welcome_text(
    *,
    bot_username: str | None,
    support_url: str | None,
    chat_url: str | None,
) -> str:
    bot_line = ""
    if bot_username:
        handle = bot_username.lstrip("@")
        bot_line = f"🤖 {_html_link(f'@{handle}', f'https://t.me/{handle}')}"

    links: list[str] = []
    if bot_line:
        links.append(bot_line)
    if _is_public_link(support_url):
        links.append(f"🛟 {_html_link('Поддержка', support_url or '')}")
    if _is_public_link(chat_url):
        links.append(f"👥 {_html_link('Чат', chat_url or '')}")
    footer = " · ".join(links)

    return (
        "💠 <b>NOVERA</b>\n"
        "<i>Digital Capital Ecosystem</i>\n\n"
        "Цифровая инвест-платформа: крипто-арбитраж, авто-обработка рыночных "
        "дисбалансов и партнёрская инфраструктура в одной экосистеме.\n\n"
        "──────────────\n\n"
        "💼 <b>Программа · 10% / 24H</b>\n"
        "• Цикл — <b>20 дней</b>\n"
        "• Начисление — <b>10% / день</b>\n"
        "• Итого — <b>200%</b> + возврат депозита на <b>20-й день</b>\n\n"
        "Пример: <b>100 USDT</b> → <b>10 USDT/день</b> → <b>200 USDT</b> за цикл.\n"
        "После цикла можно открыть новый депозит на актуальных условиях.\n\n"
        "──────────────\n\n"
        "🤝 <b>Partner Network</b>\n"
        "Доступ к уровням — по обороту 1-й линии (личный депозит не требуется).\n"
        "<code>L1 8%</code> · линия 100\n"
        "<code>L2 4%</code> · линия 300\n"
        "<code>L3 2,5%</code> · линия 500\n"
        "<code>L4 1,5%</code> · линия 1 500\n"
        "<code>L5 1%</code> · линия 5 000\n\n"
        "──────────────\n\n"
        "⚡ Арбитраж · Авто-начисления · Партнёрка"
        + (f"\n\n{footer}" if footer else "")
    )


def _telegram_user_from_message(
    message: Message,
    *,
    start_param: str | None = None,
) -> TelegramUser | None:
    source = message.from_user
    if source is None:
        return None
    return TelegramUser(
        id=source.id,
        username=source.username,
        first_name=source.first_name or "",
        language_code=source.language_code,
        start_param=start_param,
    )


async def _issue_login_token(
    repository: DeltaRepository | None,
    message: Message,
    *,
    start_param: str | None = None,
) -> str | None:
    if repository is None:
        return None
    user = _telegram_user_from_message(message, start_param=start_param)
    if user is None:
        return None
    return await repository.create_web_login_token(user)


def create_dispatcher(
    miniapp_url: str,
    *,
    repository: DeltaRepository | None = None,
    admin_ids: set[int] | frozenset[int] | None = None,
    chain_settings: Settings | None = None,
) -> Dispatcher:
    router = Router()
    admins = set(admin_ids or ())

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        language = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if language.startswith("en"):
            button = "Open NOVERA"
            support_label = "Support"
            chat_label = "Chat"
        elif language.startswith("uk"):
            button = "Відкрити NOVERA"
            support_label = "Підтримка"
            chat_label = "Чат"
        else:
            button = "Открыть NOVERA"
            support_label = "Поддержка"
            chat_label = "Чат"

        start_param = None
        if message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                start_param = parts[1].strip()[:128]

        # Bind referral at /start (not only when Mini App opens). First-touch only.
        if repository is not None and message.from_user is not None:
            referrer_id = None
            if start_param and start_param.startswith("ref_"):
                raw = start_param.removeprefix("ref_")
                if raw.isdigit():
                    referrer_id = int(raw)
            await repository.ensure_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name or "",
                message.from_user.language_code,
                referrer_id,
            )

        login_token = await _issue_login_token(
            repository,
            message,
            start_param=start_param,
        )
        launch_url = _webapp_url(miniapp_url, login_token=login_token)

        support_url = str(chain_settings.support_url) if chain_settings is not None else ""
        chat_url = str(chain_settings.chat_url) if chain_settings is not None else ""

        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=button, web_app=WebAppInfo(url=launch_url))]
        ]
        link_row: list[InlineKeyboardButton] = []
        if _is_public_link(support_url):
            link_row.append(InlineKeyboardButton(text=support_label, url=support_url))
        if _is_public_link(chat_url):
            link_row.append(InlineKeyboardButton(text=chat_label, url=chat_url))
        if link_row:
            rows.append(link_row)
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        bot_username = None
        try:
            me = await message.bot.get_me()
            bot_username = me.username
        except Exception:
            logger.debug("Unable to resolve bot username for welcome message", exc_info=True)

        text = _build_welcome_text(
            bot_username=bot_username,
            support_url=support_url,
            chat_url=chat_url,
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    async def partner_stats(message: Message) -> None:
        if repository is None or message.from_user is None:
            return
        tg_user = _telegram_user_from_message(message)
        if tg_user is not None:
            await repository.ensure_user(
                tg_user.id,
                tg_user.username,
                tg_user.first_name,
                tg_user.language_code,
                None,
            )
        team = await repository.team(message.from_user.id)
        stats = dict(team.get("stats") or {})
        earned = minor_to_text(int(stats.get("earned_minor") or 0))
        today = minor_to_text(int(stats.get("today_minor") or 0))
        available = minor_to_text(int(stats.get("available_minor") or 0))
        withdrawn = minor_to_text(int(stats.get("withdrawn_minor") or 0))
        personal = minor_to_text(int(stats.get("personal_minor") or 0))
        line = minor_to_text(int(stats.get("line_minor") or 0))
        current_level = int(stats.get("current_level") or 0)
        team_count = int(stats.get("team_count") or 0)
        text = (
            "📊 <b>NOVERA | PARTNER NETWORK</b>\n\n"
            f"💎 Доход от партнёрки: <b>{earned} USDT</b>\n"
            f"📈 Сегодня: <b>+{today} USDT</b>\n"
            f"💼 Доступно к выводу: <b>{available} USDT</b>\n"
            f"✅ Уже выведено: <b>{withdrawn} USDT</b>\n\n"
            f"◆ Личные инвестиции: <b>{personal} USDT</b>\n"
            f"◉ Оборот 1-й линии: <b>{line} USDT</b>\n"
            f"👥 В команде: <b>{team_count}</b>\n"
            f"▣ Открыто уровней: <b>{current_level}/5</b>"
        )
        goal = stats.get("next_goal")
        if isinstance(goal, dict):
            rate = float(int(goal.get("rate_bps") or 0)) / 100
            remaining_personal = int(goal.get("remaining_personal_minor") or 0)
            remaining_line = int(goal.get("remaining_line_minor") or 0)
            text += (
                "\n\n🎯 <b>Следующая цель</b>\n"
                f"LEVEL {int(goal.get('level') or 0):02d} — <b>{rate:g}%</b>"
            )
            if remaining_personal > 0:
                text += (
                    f"\nОсталось личного депозита: <b>{minor_to_text(remaining_personal)} USDT</b>"
                )
            if remaining_line > 0:
                text += (
                    f"\nОсталось оборота линии: <b>{minor_to_text(remaining_line)} USDT</b>"
                )
            if remaining_personal <= 0 and remaining_line <= 0:
                text += "\nУсловия следующей цели уже выполнены."
        else:
            text += "\n\n🏆 <b>Все 5 уровней открыты.</b>"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть партнёрскую программу",
                    web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="team")),
                )
            ]]
        )
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @router.message(Command("stats"))
    async def stats_command(message: Message) -> None:
        await partner_stats(message)

    @router.message(Command("team"))
    async def team_command(message: Message) -> None:
        await partner_stats(message)

    @router.message(Command("admin"))
    async def admin(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        dynamic_admin = bool(repository is not None and user_id and await repository.is_granted_admin(user_id))
        if not user_id or (user_id not in admins and not dynamic_admin):
            return
        summary = await repository.admin_summary() if repository is not None else {}
        deposited = minor_to_text(int(summary.get("deposited_minor", 0)))
        paid = minor_to_text(int(summary.get("paid_minor", 0)))
        active = minor_to_text(int(summary.get("active_principal_minor", 0)))
        text = (
            "🛠 <b>NOVERA · Админ-панель</b>\n\n"
            f"👥 Пользователей: <b>{summary.get('users', 0)}</b> "
            f"(активных 7 дн.: {summary.get('active_users_7d', 0)}, за сутки: +{summary.get('new_users_24h', 0)})\n"
            f"📥 Депозиты: <b>{deposited} USDT</b>\n"
            f"📤 Выплачено: <b>{paid} USDT</b>\n"
            f"📈 Активных депозитов: <b>{summary.get('active_deposits', 0)}</b> на {active} USDT\n"
            f"⚠️ Проблемных выплат: <b>{summary.get('failed_payouts', 0)}</b>\n\n"
            "Расширенное управление доступно в защищённой Mini App."
        )
        login_token = await _issue_login_token(repository, message)
        rows = [
            [
                InlineKeyboardButton(text="👥 Пользователи", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="users", login_token=login_token))),
                InlineKeyboardButton(text="🔎 Поиск", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="users", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="📈 Депозиты", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="deposits", login_token=login_token))),
                InlineKeyboardButton(text="💳 Выплаты", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="payouts", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="⚠️ Проблемные выплаты", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="payouts", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="overview", login_token=login_token))),
                InlineKeyboardButton(text="🏦 Казна", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="treasury", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="💰 Тарифы", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="terms", login_token=login_token))),
                InlineKeyboardButton(text="📣 Рассылка", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="broadcasts", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="🛡 Администраторы", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="admins", login_token=login_token))),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="system", login_token=login_token))),
                InlineKeyboardButton(text="📜 Логи", web_app=WebAppInfo(url=_webapp_url(miniapp_url, view="admin", tab="logs", login_token=login_token))),
            ],
        ]
        await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_launcher(
    bot_token: str,
    miniapp_url: str,
    *,
    repository: DeltaRepository | None = None,
    admin_ids: set[int] | frozenset[int] | None = None,
    chain_settings: Settings | None = None,
) -> None:
    delay = 2
    while True:
        bot = Bot(bot_token)
        dispatcher = create_dispatcher(
            miniapp_url,
            repository=repository,
            admin_ids=admin_ids,
            chain_settings=chain_settings,
        )
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Открыть NOVERA",
                    web_app=WebAppInfo(url=miniapp_url),
                )
            )
            delay = 2
            await dispatcher.start_polling(bot, handle_signals=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Telegram launcher disconnected: %s; retrying in %ss",
                type(exc).__name__,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        finally:
            await bot.session.close()
