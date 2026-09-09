"""Fire-and-forget deposit/payout alerts to an ops Telegram chat/topic."""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from ..amounts import minor_to_text
from ..config import Settings

logger = logging.getLogger(__name__)


class OpsChatSettingsStore(Protocol):
    async def get_ops_chat_settings(
        self, *, env_chat_id: int | None = None, env_topic_id: int | None = None
    ) -> dict[str, object]: ...


def format_user_line(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> str:
    clean_username = str(username or "").strip().lstrip("@")
    if clean_username:
        return f"@{html.escape(clean_username)}"
    clean_name = str(first_name or "").strip()
    if clean_name:
        return html.escape(clean_name)
    return f"ID {int(telegram_id)}"


def explorer_tx_url(template: str, tx_hash: str) -> str:
    return str(template).replace("{tx_hash}", str(tx_hash))


def payout_kind_label(kind: str, subtype: str | None = None) -> str:
    kind_key = str(kind or "").strip().lower()
    subtype_key = str(subtype or "").strip().lower()
    if kind_key == "referral":
        return "партнёрский вывод"
    if subtype_key == "principal":
        return "возврат тела"
    if kind_key == "daily":
        return "дневная"
    return kind_key or "выплата"


def format_deposit_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    deposit_id: int,
    tx_hash: str | None = None,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    lines = [
        "💎 <b>Новый депозит</b>",
        f"👤 {user_line} · <code>{int(telegram_id)}</code>",
        f"💰 Сумма: <b>{amount} USDT</b>",
        f"📦 Депозит #{int(deposit_id)}",
    ]
    clean_tx = str(tx_hash or "").strip()
    if clean_tx:
        url = html.escape(explorer_tx_url(explorer_template, clean_tx))
        lines.append(f'🔗 <a href="{url}">Транзакция</a>')
    return "\n".join(lines)


def format_payout_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    tx_hash: str,
    kind: str,
    subtype: str | None = None,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    label = html.escape(payout_kind_label(kind, subtype))
    clean_tx = str(tx_hash).strip()
    url = html.escape(explorer_tx_url(explorer_template, clean_tx))
    short = html.escape(clean_tx if len(clean_tx) <= 18 else f"{clean_tx[:10]}…{clean_tx[-6:]}")
    return "\n".join(
        [
            f"💸 <b>Выплата</b> · {label}",
            f"👤 {user_line} · <code>{int(telegram_id)}</code>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f'🔗 <a href="{url}">{short}</a>',
        ]
    )


def env_ops_chat_id(settings: Settings) -> int | None:
    chat_id = settings.ops_chat_id
    if chat_id is None and settings.log_channel_id is not None:
        chat_id = settings.log_channel_id
    return int(chat_id) if chat_id is not None else None


def env_ops_topic_id(settings: Settings) -> int | None:
    if settings.ops_topic_id is None:
        return None
    return int(settings.ops_topic_id)


class OpsChatNotifier:
    """Send deposit/payout alerts; DB admin settings override env fallback."""

    def __init__(
        self,
        settings: Settings,
        bot_token: str,
        repository: OpsChatSettingsStore | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.bot = Bot(bot_token)

    async def resolve_target(self) -> tuple[int | None, int | None]:
        env_chat = env_ops_chat_id(self.settings)
        env_topic = env_ops_topic_id(self.settings)
        if self.repository is not None:
            cfg = await self.repository.get_ops_chat_settings(
                env_chat_id=env_chat,
                env_topic_id=env_topic,
            )
            if not cfg.get("active"):
                return None, None
            chat_id = cfg.get("chat_id")
            topic_id = cfg.get("topic_id")
            return (
                int(chat_id) if chat_id is not None else None,
                int(topic_id) if topic_id is not None else None,
            )
        if env_chat is None:
            return None, None
        return env_chat, env_topic

    async def close(self) -> None:
        await self.bot.session.close()

    async def _send(self, text: str, *, preview: bool) -> None:
        chat_id, topic_id = await self.resolve_target()
        if chat_id is None:
            return
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": not preview,
        }
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        try:
            await self.bot.send_message(**kwargs)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(min(float(exc.retry_after), 5.0))
            try:
                await self.bot.send_message(**kwargs)
            except Exception as retry_exc:
                logger.warning(
                    "Ops chat retry failed: %s", type(retry_exc).__name__
                )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logger.warning("Ops chat rejected message: %s", type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Ops chat delivery failed: %s", type(exc).__name__)

    async def notify_deposit(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        amount_minor: int,
        deposit_id: int,
        tx_hash: str | None = None,
    ) -> None:
        text = format_deposit_ops_html(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            amount_minor=amount_minor,
            deposit_id=deposit_id,
            tx_hash=tx_hash,
            explorer_template=self.settings.block_explorer_tx_url,
        )
        await self._send(text, preview=False)

    async def notify_payout(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        amount_minor: int,
        tx_hash: str,
        kind: str,
        subtype: str | None = None,
    ) -> None:
        text = format_payout_ops_html(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            amount_minor=amount_minor,
            tx_hash=tx_hash,
            kind=kind,
            subtype=subtype,
            explorer_template=self.settings.block_explorer_tx_url,
        )
        await self._send(text, preview=True)
