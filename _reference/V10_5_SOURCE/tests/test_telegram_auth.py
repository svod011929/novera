import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from delta_backend.telegram_auth import TelegramAuthError, validate_init_data


TOKEN = "123456:TEST_TOKEN"


def signed_init_data(*, auth_date: int = 1_700_000_000) -> str:
    values = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "signature": "telegram-third-party-signature",
        "user": json.dumps(
            {
                "id": 42,
                "first_name": "Daniil",
                "username": "delta_user",
                "language_code": "ru",
            },
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_init_data() -> None:
    user = validate_init_data(
        signed_init_data(),
        TOKEN,
        max_age_seconds=3600,
        now=1_700_000_100,
    )
    assert user.id == 42
    assert user.username == "delta_user"


def test_rejects_tampered_init_data() -> None:
    source = signed_init_data().replace("delta_user", "attacker")
    with pytest.raises(TelegramAuthError):
        validate_init_data(source, TOKEN, now=1_700_000_100)


def test_rejects_expired_init_data() -> None:
    with pytest.raises(TelegramAuthError, match="expired"):
        validate_init_data(
            signed_init_data(),
            TOKEN,
            max_age_seconds=60,
            now=1_700_000_100,
        )


def test_signed_old_init_data_allowed_when_age_check_disabled() -> None:
    now = 2_000_000_000
    init_data = signed_init_data(auth_date=now - 86_400 * 30)
    user = validate_init_data(init_data, TOKEN, max_age_seconds=0, now=now)
    assert user.id == 42
