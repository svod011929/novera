import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


# NOVERA Telegram per-user storage authentication


class TelegramAuthError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class TelegramUser:
    id: int
    username: str | None
    first_name: str
    language_code: str | None
    start_param: str | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int | None = 3600,  # None or 0 disables the age check
    now: int | None = None,
) -> TelegramUser:
    if not init_data:
        raise TelegramAuthError("Telegram initData is missing")
    if not bot_token:
        raise TelegramAuthError("Bot token is not configured")

    values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    received_hash = values.pop("hash", "")
    if len(received_hash) != 64:
        raise TelegramAuthError("Telegram hash is missing or malformed")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramAuthError("Telegram initData signature is invalid")

    current_time = int(time.time()) if now is None else now
    try:
        auth_date = int(values["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramAuthError("Telegram auth_date is missing") from exc
    if auth_date > current_time + 300:
        raise TelegramAuthError("Telegram auth_date is in the future")
    # ``None`` or ``0`` disables the age check; production settings validate
    # the TTL to 60..86400 seconds, so this only affects explicit callers.
    if max_age_seconds and current_time - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram initData has expired")

    try:
        raw_user = json.loads(values["user"])
        telegram_id = int(raw_user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("Telegram user data is malformed") from exc

    return TelegramUser(
        id=telegram_id,
        username=raw_user.get("username"),
        first_name=str(raw_user.get("first_name") or ""),
        language_code=raw_user.get("language_code"),
        start_param=values.get("start_param"),
    )
