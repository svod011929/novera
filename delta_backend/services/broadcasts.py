import asyncio
import json
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from ..repository import DeltaRepository


logger = logging.getLogger(__name__)


class BroadcastService:
    def __init__(self, repository: DeltaRepository, bot_token: str) -> None:
        self.repository = repository
        self.bot = Bot(bot_token)

    async def close(self) -> None:
        await self.bot.session.close()

    @staticmethod
    def _keyboard(raw: object) -> InlineKeyboardMarkup | None:
        if not raw:
            return None
        try:
            items = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        rows: list[list[InlineKeyboardButton]] = []
        if not isinstance(items, list):
            return None
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()[:64]
            url = str(item.get("url") or "").strip()[:2048]
            if not text or not url:
                continue
            rows.append([InlineKeyboardButton(text=text, url=url)])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    async def _send_delivery(self, delivery: dict[str, object]) -> None:
        chat_id = int(delivery["user_id"])
        message = str(delivery.get("message") or "")
        parse_mode = str(delivery.get("parse_mode") or "HTML") or None
        keyboard = self._keyboard(delivery.get("buttons_json"))
        media_file_id = str(delivery.get("media_file_id") or "").strip()
        media_path = str(delivery.get("media_path") or "").strip()

        if media_file_id or media_path:
            photo: str | FSInputFile
            using_local_file = not media_file_id
            if media_file_id:
                photo = media_file_id
            else:
                path = Path(media_path)
                if not path.is_file():
                    raise FileNotFoundError("Broadcast image is missing")
                photo = FSInputFile(path)

            if message and len(message) <= 1024:
                sent = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=message,
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            else:
                sent = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                )
                if message:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=parse_mode,
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                elif keyboard is not None:
                    # Telegram cannot attach a keyboard to an already-sent message;
                    # send a compact zero-width text carrier for image-only broadcasts.
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text="\u2063",
                        reply_markup=keyboard,
                    )

            if using_local_file and getattr(sent, "photo", None):
                photos = sent.photo or []
                if photos:
                    await self.repository.set_broadcast_media_file_id(
                        int(delivery["broadcast_id"]),
                        str(photos[-1].file_id),
                    )
            return

        if not message:
            raise ValueError("Broadcast message is empty")
        await self.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=parse_mode,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                delivery = await self.repository.claim_next_broadcast_delivery()
                if delivery is None:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                    except TimeoutError:
                        pass
                    continue

                delivery_id = int(delivery["id"])
                try:
                    await self._send_delivery(delivery)
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(min(float(exc.retry_after), 30.0))
                    await self.repository.requeue_broadcast_delivery(
                        delivery_id,
                        "Telegram rate limit",
                    )
                except (TelegramForbiddenError, TelegramBadRequest) as exc:
                    await self.repository.finish_broadcast_delivery(
                        delivery_id,
                        delivered=False,
                        error=type(exc).__name__,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Broadcast delivery failed: delivery=%s error=%s",
                        delivery_id,
                        type(exc).__name__,
                    )
                    await self.repository.finish_broadcast_delivery(
                        delivery_id,
                        delivered=False,
                        error=type(exc).__name__,
                    )
                else:
                    await self.repository.finish_broadcast_delivery(
                        delivery_id,
                        delivered=True,
                    )
                await asyncio.sleep(0.06)
        finally:
            await self.close()
