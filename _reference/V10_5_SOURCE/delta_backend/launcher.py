import asyncio
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
from .repository import DeltaRepository
from .telegram_auth import TelegramUser

logger = logging.getLogger(__name__)
# GFORT V10.3 partner statistics command + notification entry point


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
) -> Dispatcher:
    router = Router()
    admins = set(admin_ids or ())

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        language = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if language.startswith("en"):
            button = "Open GFORT"
        elif language.startswith("uk"):
            button = "Відкрити GFORT"
        else:
            button = "Открыть GFORT"

        start_param = None
        if message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                start_param = parts[1].strip()[:128]

        login_token = await _issue_login_token(
            repository,
            message,
            start_param=start_param,
        )
        launch_url = _webapp_url(miniapp_url, login_token=login_token)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button, web_app=WebAppInfo(url=launch_url))]
            ]
        )

        text = (
            "⚫️ <b>GFORT | DIGITAL ARBITRAGE ECOSYSTEM</b>\n\n"
            '<a href="https://t.me/GFORTROBOT">🤖 @GFORTROBOT</a>\n\n'
            "◼︎ <b>О GFORT</b>\n\n"
            "GFORT — цифровая инвестиционная платформа, ориентированная на использование возможностей "
            "криптовалютного арбитража и автоматизированных торговых механизмов.\n\n"
            "Платформа анализирует котировки цифровых активов на различных торговых площадках, "
            "выявляя ценовые расхождения и потенциальные арбитражные возможности.\n\n"
            "Автоматизированные алгоритмы позволяют обрабатывать рыночные данные и использовать "
            "возникающие дисбалансы между криптовалютными площадками.\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "💼 <b>ИНВЕСТИЦИОННАЯ ПРОГРАММА</b>\n\n"
            "<b>10% / 24H</b>\n\n"
            "• Инвестиционный цикл — <b>20 дней</b>\n"
            "• Ежедневное начисление — <b>10%</b>\n"
            "• Общая сумма начислений — <b>200%</b>\n\n"
            "<b>Пример:</b>\n\n"
            "Инвестиция <b>100 USDT</b>\n"
            "→ <b>10 USDT</b> ежедневного начисления\n"
            "→ <b>20 дней</b>\n"
            "→ <b>200 USDT</b> начислений за полный цикл.\n"
            "Ваш депозит будет выплачен на 20 день.\n\n"
            "После завершения цикла пользователь может открыть новый депозит на условиях, "
            "действующих на платформе.\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "◼︎ <b>PARTNER NETWORK</b>\n\n"
            "Развивайте собственную партнёрскую сеть и открывайте дополнительные уровни вознаграждений.\n\n"
            "<b>LEVEL 01 — 8%</b>\n"
            "Личный депозит: <b>50 USDT</b>\n"
            "Объём 1-й линии: <b>100 USDT</b>\n\n"
            "<b>LEVEL 02 — 4%</b>\n"
            "Личный депозит: <b>100 USDT</b>\n"
            "Объём 1-й линии: <b>300 USDT</b>\n\n"
            "<b>LEVEL 03 — 2,5%</b>\n"
            "Личный депозит: <b>300 USDT</b>\n"
            "Объём 1-й линии: <b>500 USDT</b>\n\n"
            "<b>LEVEL 04 — 1,5%</b>\n"
            "Личный депозит: <b>500 USDT</b>\n"
            "Объём 1-й линии: <b>1 500 USDT</b>\n\n"
            "<b>LEVEL 05 — 1%</b>\n"
            "Личный депозит: <b>1 000 USDT</b>\n"
            "Объём 1-й линии: <b>5 000 USDT</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ <b>GFORT ECOSYSTEM</b>\n\n"
            "<b>Automated Infrastructure</b>\n"
            "Автоматизированная обработка операций и рыночных данных.\n\n"
            "<b>Arbitrage Analytics</b>\n"
            "Анализ ценовых расхождений между криптовалютными площадками.\n\n"
            "<b>Automated Processing</b>\n"
            "Системная обработка начислений и операций.\n\n"
            "<b>Partner Infrastructure</b>\n"
            "Инструменты для построения и развития собственной партнёрской сети.\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "◼︎ <b>ENTER GFORT</b>\n\n"
            "GFORT объединяет криптовалютный арбитраж, автоматизированную инфраструктуру и "
            "партнёрские инструменты в единой цифровой экосистеме.\n\n"
            '<a href="https://t.me/GFORTROBOT">🤖 @GFORTROBOT</a>\n'
            '<a href="https://t.me/+CKR1x-wkWZNiNTYx">👥 GFORT Community</a>'
        )
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
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
            "📊 <b>GFORT | PARTNER NETWORK</b>\n\n"
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
            text += (
                "\n\n🎯 <b>Следующая цель</b>\n"
                f"LEVEL {int(goal.get('level') or 0):02d} — <b>{rate:g}%</b>\n"
                f"Осталось личного депозита: <b>{minor_to_text(int(goal.get('remaining_personal_minor') or 0))} USDT</b>\n"
                f"Осталось оборота линии: <b>{minor_to_text(int(goal.get('remaining_line_minor') or 0))} USDT</b>"
            )
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
            "🛠 <b>GFORT · Админ-панель</b>\n\n"
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
) -> None:
    delay = 2
    while True:
        bot = Bot(bot_token)
        dispatcher = create_dispatcher(
            miniapp_url,
            repository=repository,
            admin_ids=admin_ids,
        )
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Открыть GFORT",
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
