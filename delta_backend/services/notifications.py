import asyncio
import json
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..repository import DeltaRepository

logger = logging.getLogger(__name__)


class UserNotificationService:
    """Deliver durable user notifications through the NOVERA Telegram bot.

    The same notification stays available in the Mini App even when Telegram
    delivery is impossible (bot muted/blocked, temporary Telegram error, etc.).
    """

    def __init__(self, repository: DeltaRepository, bot_token: str, miniapp_url: str) -> None:
        self.repository = repository
        self.bot = Bot(bot_token)
        self.miniapp_url = miniapp_url

    async def close(self) -> None:
        await self.bot.session.close()

    def _keyboard(self, delivery: dict[str, object]) -> InlineKeyboardMarkup:
        target = "home"
        try:
            data = json.loads(str(delivery.get("data_json") or "{}"))
            if isinstance(data, dict):
                target = str(data.get("target_view") or "home")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        separator = "&" if "?" in self.miniapp_url else "?"
        url = f"{self.miniapp_url}{separator}view={target}"
        return InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть NOVERA",
                    web_app=WebAppInfo(url=url),
                )
            ]]
        )

    async def _send(self, delivery: dict[str, object]) -> None:
        await self.bot.send_message(
            chat_id=int(delivery["user_id"]),
            text=str(delivery.get("telegram_html") or delivery.get("body") or "NOVERA"),
            parse_mode="HTML",
            reply_markup=self._keyboard(delivery),
            disable_web_page_preview=True,
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                delivery = await self.repository.claim_next_notification_delivery()
                if delivery is None:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                    except TimeoutError:
                        pass
                    continue
                notification_id = int(delivery["id"])
                try:
                    await self._send(delivery)
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(min(float(exc.retry_after), 30.0))
                    await self.repository.requeue_notification_delivery(
                        notification_id,
                        "Telegram rate limit",
                    )
                except (TelegramForbiddenError, TelegramBadRequest) as exc:
                    await self.repository.finish_notification_delivery(
                        notification_id,
                        delivered=False,
                        error=type(exc).__name__,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "User notification delivery failed: id=%s error=%s",
                        notification_id,
                        type(exc).__name__,
                    )
                    await self.repository.requeue_notification_delivery(
                        notification_id,
                        type(exc).__name__,
                    )
                else:
                    await self.repository.finish_notification_delivery(
                        notification_id,
                        delivered=True,
                    )
                await asyncio.sleep(0.08)
        finally:
            await self.close()
