import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import signal
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from eth_account import Account
from web3 import Web3

from .amounts import MINOR_FACTOR, minor_to_atomic, minor_to_text, usdt_to_minor
from .api_settings import MiniAppSettings
from .config import Settings
from .launcher import run_launcher
from .repository import DeltaRepository, RepositoryError
from .services.blockchain import EvmTokenClient
from .services.broadcasts import BroadcastService
from .services.notifications import UserNotificationService
from .services.deposit_monitor import DepositMonitor
from .services.payouts import DailyPayoutService
from .services.safety import PayoutCircuitBreaker, SafetyMonitor, SafetyRuntime
from .telegram_auth import TelegramAuthError, TelegramUser, validate_init_data
# GFORT V10.1 admin inviter management
# GFORT V10.2 real admin treasury test payouts
# GFORT V10.3 Telegram bot + in-app notifications
# GFORT V10.4 production safety monitor + payout circuit breaker
# GFORT V10.6 audited admin financial and partner controls


logger = logging.getLogger(__name__)
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
BROADCAST_MEDIA_ID_RE = re.compile(r"^[a-f0-9]{32}\.(?:jpg|png)$")
BROADCAST_MEDIA_MAX_BYTES = 5 * 1024 * 1024


SESSION_COOKIE_NAME = "delta_session"
# GFORT V10 Telegram per-user storage authentication
SESSION_TOKEN_VERSION = 1
CLIENT_SESSION_TTL_SECONDS = 90 * 24 * 60 * 60

# GFORT V9.4 account-safe native authentication


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _web_session_key(bot_token: str) -> bytes:
    return hmac.new(
        b"DELTA-MiniApp-Session-v1",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def issue_web_session(
    user: TelegramUser,
    bot_token: str,
    ttl_seconds: int,
    *,
    now: int | None = None,
) -> str:
    current_time = int(time.time()) if now is None else now
    payload = {
        "v": SESSION_TOKEN_VERSION,
        "uid": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "language_code": user.language_code,
        "iat": current_time,
        "exp": current_time + ttl_seconds,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_web_session_key(bot_token), raw, hashlib.sha256).digest()
    return f"{_b64url_encode(raw)}.{_b64url_encode(signature)}"


def validate_web_session(
    token: str,
    bot_token: str,
    *,
    now: int | None = None,
) -> TelegramUser:
    if not token or len(token) > 4096:
        raise TelegramAuthError("GFORT session is missing")
    try:
        raw_part, signature_part = token.split(".", 1)
        raw = _b64url_decode(raw_part)
        received_signature = _b64url_decode(signature_part)
    except Exception as exc:
        raise TelegramAuthError("GFORT session is malformed") from exc
    expected_signature = hmac.new(_web_session_key(bot_token), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(received_signature, expected_signature):
        raise TelegramAuthError("GFORT session signature is invalid")
    try:
        payload = json.loads(raw.decode("utf-8"))
        version = int(payload["v"])
        user_id = int(payload["uid"])
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("GFORT session payload is invalid") from exc
    current_time = int(time.time()) if now is None else now
    if version != SESSION_TOKEN_VERSION or issued_at > current_time + 30 or expires_at <= current_time:
        raise TelegramAuthError("GFORT session has expired")
    if expires_at - issued_at > 7_776_000:
        raise TelegramAuthError("GFORT session lifetime is invalid")
    return TelegramUser(
        id=user_id,
        username=payload.get("username"),
        first_name=str(payload.get("first_name") or ""),
        language_code=payload.get("language_code"),
    )



class WalletRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)


class InvoiceRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class SessionExchangeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class BlockRequest(BaseModel):
    blocked: bool


class AdminGrantRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)


class AdminUserBalanceRequest(BaseModel):
    balance_usdt: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)


class AdminUserWalletRequest(BaseModel):
    address: str | None = Field(default=None, max_length=42)


class AdminUserReferrerRequest(BaseModel):
    identifier: str | None = Field(default=None, max_length=64)


class AdminReferralBalanceRequest(BaseModel):
    balance_usdt: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)


class AdminReferralLevelRequest(BaseModel):
    unlocked_level: int = Field(ge=0, le=5)
    reason: str = Field(min_length=2, max_length=500)


class AdminOpenInvestmentRequest(BaseModel):
    amount_usdt: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    reason: str = Field(min_length=2, max_length=500)
    operation_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    confirm: Literal["OPEN_INVESTMENT"]


class AdminTestPayoutRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    amount: Decimal = Field(ge=Decimal("1"), le=Decimal("1000000000000"))
    confirm: Literal["REAL_PAYOUT"]


class BroadcastButtonRequest(BaseModel):
    text: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=4, max_length=2048)


class BroadcastRequest(BaseModel):
    message: str = Field(default="", max_length=4096)
    audience: Literal["all", "investors", "partners"] = "all"
    media_id: str | None = Field(default=None, max_length=64)
    buttons: list[BroadcastButtonRequest] = Field(default_factory=list, max_length=8)


class BroadcastMediaUploadRequest(BaseModel):
    mime_type: Literal["image/jpeg", "image/png"]
    data_base64: str = Field(min_length=16)


class RuntimeSettingsRequest(BaseModel):
    daily_profit_bps: int = Field(ge=1, le=10000)
    payout_days: int = Field(ge=1, le=20)
    deposit_min_usdt: int = Field(ge=1, le=1000000000)
    deposit_max_usdt: int = Field(ge=1, le=1000000000)
    invoice_ttl_minutes: int = Field(ge=1, le=1440)
    referral_level_bps: list[int] = Field(min_length=5, max_length=5)
    referral_personal_thresholds_usdt: list[int] = Field(min_length=5, max_length=5)
    referral_line_thresholds_usdt: list[int] = Field(min_length=5, max_length=5)
    deposits_enabled: bool
    payouts_enabled: bool
    confirmation_blocks: int = Field(ge=0, le=100)
    deposit_scan_interval_seconds: int = Field(ge=1, le=3600)
    support_url: str = Field(min_length=4, max_length=512)
    chat_url: str = Field(min_length=4, max_length=512)


class ChainRuntimeConfigRequest(BaseModel):
    mode: Literal["production", "testnet", "off"]
    token_contract: str = Field(min_length=42, max_length=42)
    scan_start_block: int = Field(ge=0, le=10_000_000_000)
    rpc_url: str | None = Field(default=None, max_length=4096)
    wss_url: str | None = Field(default=None, max_length=4096)
    seed_phrase: str | None = Field(default=None, max_length=512)


class AuthenticatedUser(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str
    is_admin: bool


@dataclass(slots=True)
class RuntimeStatus:
    started_at: float = field(default_factory=time.time)
    last_payout_tick: float | None = None
    last_payout_error: str | None = None


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        threshold = now - window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0])) + 1)
            events.append(now)
            if len(self._events) > 10_000:
                empty = [name for name, values in self._events.items() if not values]
                for name in empty[:1000]:
                    self._events.pop(name, None)
        return None


class _TelegramHTMLSanitizer(HTMLParser):
    allowed_tags = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        if tag == "a":
            href = next((value for name, value in attrs if name.lower() == "href"), None)
            href = (href or "").strip()
            if not href.startswith(("https://", "http://", "tg://")):
                return
            self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
            self.open_tags.append(tag)
            return
        self.parts.append(f"<{tag}>")
        self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.open_tags or tag not in self.open_tags:
            return
        while self.open_tags:
            current = self.open_tags.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def close_open_tags(self) -> None:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")


def sanitize_telegram_html(value: str) -> str:
    parser = _TelegramHTMLSanitizer()
    try:
        parser.feed(value)
        parser.close()
        parser.close_open_tags()
    except Exception:
        return html.escape(value, quote=False)
    return "".join(parser.parts).strip()


def validate_broadcast_buttons(buttons: list[BroadcastButtonRequest]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for button in buttons:
        text = button.text.strip()
        url = button.url.strip()
        if not url.startswith(("https://", "http://", "tg://")):
            raise HTTPException(status_code=422, detail="Button URL must use https://, http:// or tg://")
        result.append({"text": text, "url": url})
    return result


def runtime_settings_snapshot(business: MiniAppSettings, chain_settings: Settings) -> dict[str, object]:
    return {
        "daily_profit_bps": int(business.daily_profit_bps),
        "payout_days": int(business.payout_days),
        "deposit_min_usdt": int(business.deposit_min_usdt),
        "deposit_max_usdt": int(business.deposit_max_usdt),
        "invoice_ttl_minutes": int(business.invoice_ttl_minutes),
        "referral_level_bps": list(business.referral_level_bps),
        "referral_personal_thresholds_usdt": list(business.referral_personal_thresholds_usdt),
        "referral_line_thresholds_usdt": list(business.referral_line_thresholds_usdt),
        "deposits_enabled": bool(chain_settings.deposits_enabled),
        "payouts_enabled": bool(chain_settings.payouts_enabled),
        "confirmation_blocks": int(chain_settings.confirmation_blocks),
        "deposit_scan_interval_seconds": int(chain_settings.deposit_scan_interval_seconds),
        "support_url": str(chain_settings.support_url),
        "chat_url": str(chain_settings.chat_url),
    }


def apply_runtime_settings(
    business: MiniAppSettings,
    chain_settings: Settings,
    values: dict[str, object],
) -> None:
    business_fields = {
        "daily_profit_bps", "payout_days", "deposit_min_usdt", "deposit_max_usdt",
        "invoice_ttl_minutes", "referral_level_bps",
        "referral_personal_thresholds_usdt", "referral_line_thresholds_usdt",
    }
    chain_fields = {
        "deposits_enabled", "payouts_enabled", "confirmation_blocks",
        "deposit_scan_interval_seconds", "support_url", "chat_url", "environment",
        "chain_enabled", "simulate_payouts", "chain_id", "token_contract",
        "treasury_address", "scan_start_block",
    }
    for key, value in values.items():
        if key in business_fields:
            if key.startswith("referral_"):
                value = tuple(int(item) for item in value)
            setattr(business, key, value)
        elif key in chain_fields:
            setattr(chain_settings, key, value)


def validate_runtime_settings_payload(payload: RuntimeSettingsRequest) -> None:
    if payload.deposit_max_usdt < payload.deposit_min_usdt:
        raise HTTPException(status_code=422, detail="Maximum deposit must be greater than or equal to minimum")
    if any(item < 0 or item > 10000 for item in payload.referral_level_bps):
        raise HTTPException(status_code=422, detail="Referral rates must be between 0 and 10000 bps")
    if any(item < 0 for item in payload.referral_personal_thresholds_usdt + payload.referral_line_thresholds_usdt):
        raise HTTPException(status_code=422, detail="Referral thresholds cannot be negative")
    if not payload.support_url.startswith(("https://", "http://", "tg://")):
        raise HTTPException(status_code=422, detail="Support URL is invalid")
    if not payload.chat_url.startswith(("https://", "http://", "tg://")):
        raise HTTPException(status_code=422, detail="Chat URL is invalid")


RUNTIME_SECRET_FILENAMES = {
    "rpc": "bsc_rpc_url.txt",
    "wss": "bsc_wss_url.txt",
    "seed": "seed_phrase.txt",
}


def _runtime_secret_dir(chain_settings: Settings) -> Path:
    return Path(chain_settings.database_path).parent / "runtime_secrets"


def _runtime_secret_path(chain_settings: Settings, kind: str) -> Path:
    return _runtime_secret_dir(chain_settings) / RUNTIME_SECRET_FILENAMES[kind]


def _read_runtime_secret(chain_settings: Settings, kind: str) -> str:
    path = _runtime_secret_path(chain_settings, kind)
    try:
        if not path.is_file() or path.stat().st_size > 65_536:
            return ""
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_runtime_secret(chain_settings: Settings, kind: str, value: str) -> None:
    root = _runtime_secret_dir(chain_settings)
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    path = _runtime_secret_path(chain_settings, kind)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temp.write_text(value.strip() + "\n", encoding="utf-8")
    try:
        temp.chmod(0o600)
        os.replace(temp, path)
        path.chmod(0o600)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def apply_runtime_secret_overrides(chain_settings: Settings) -> None:
    rpc = _read_runtime_secret(chain_settings, "rpc")
    wss = _read_runtime_secret(chain_settings, "wss")
    seed = _read_runtime_secret(chain_settings, "seed")
    if rpc:
        chain_settings.bsc_rpc_url = rpc
    if wss:
        chain_settings.bsc_wss_url = wss
    if seed:
        chain_settings.payout_seed_phrase = SecretStr(seed)
        chain_settings.payout_private_key = None
        chain_settings.payout_keystore_path = None
        chain_settings.payout_keystore_password = None


def _provider_label(url: str) -> str:
    if not url:
        return "not configured"
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or "configured"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"
    except Exception:
        return "configured"


def validate_chain_runtime_candidate(candidate: Settings) -> None:
    if candidate.environment not in {"production", "testnet", "development"}:
        raise HTTPException(status_code=422, detail="Invalid chain environment")

    phrase = candidate.payout_seed_phrase.get_secret_value().strip() if candidate.payout_seed_phrase else ""
    has_private_key = bool(candidate.payout_private_key and candidate.payout_private_key.get_secret_value().strip())
    has_keystore = bool(candidate.payout_keystore_path and candidate.payout_keystore_password)
    if phrase:
        if len(phrase.split()) not in {12, 15, 18, 21, 24}:
            raise HTTPException(status_code=422, detail="Seed phrase must contain 12, 15, 18, 21 or 24 words")
        try:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(phrase, account_path=candidate.seed_account_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Seed phrase cannot derive an EVM wallet") from exc
        candidate.treasury_address = account.address

    if not candidate.chain_enabled:
        return
    if candidate.environment == "production" and candidate.chain_id != 56:
        raise HTTPException(status_code=422, detail="Production mode requires BSC Mainnet chain ID 56")
    if candidate.environment == "testnet" and candidate.chain_id != 97:
        raise HTTPException(status_code=422, detail="Testnet mode requires BSC Testnet chain ID 97")
    if candidate.simulate_payouts:
        raise HTTPException(status_code=422, detail="Live chain mode cannot simulate payouts")
    if not Web3.is_address(candidate.token_contract):
        raise HTTPException(status_code=422, detail="Invalid token contract address")
    if not Web3.is_address(candidate.treasury_address):
        raise HTTPException(status_code=422, detail="Invalid treasury wallet address")
    if candidate.environment == "production" and int(candidate.scan_start_block) <= 0:
        raise HTTPException(status_code=422, detail="Production mode requires a positive scan start block")
    if candidate.environment == "production":
        if not candidate.bsc_rpc_url.startswith("https://"):
            raise HTTPException(status_code=422, detail="Production RPC must use https://")
        if not candidate.bsc_wss_url.startswith("wss://"):
            raise HTTPException(status_code=422, detail="Production WSS must use wss://")
    else:
        if not candidate.bsc_rpc_url.startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="RPC must use http:// or https://")
        if not candidate.bsc_wss_url.startswith(("wss://", "ws://")):
            raise HTTPException(status_code=422, detail="WSS must use ws:// or wss://")
    if not phrase and not has_private_key and not has_keystore:
        raise HTTPException(status_code=422, detail="A payout signing method is required")


def chain_runtime_snapshot(chain_settings: Settings) -> dict[str, object]:
    phrase = chain_settings.payout_seed_phrase.get_secret_value().strip() if chain_settings.payout_seed_phrase else ""
    mode = "off"
    if chain_settings.chain_enabled:
        mode = "production" if chain_settings.environment == "production" and chain_settings.chain_id == 56 else "testnet"
    return {
        "mode": mode,
        "chain_id": int(chain_settings.chain_id),
        "token_contract": chain_settings.token_contract,
        "treasury_address": chain_settings.treasury_address,
        "scan_start_block": int(chain_settings.scan_start_block),
        "rpc_provider": _provider_label(chain_settings.bsc_rpc_url),
        "wss_provider": _provider_label(chain_settings.bsc_wss_url),
        "rpc_configured": bool(chain_settings.bsc_rpc_url),
        "wss_configured": bool(chain_settings.bsc_wss_url),
        "seed_configured": bool(phrase),
        "runtime_rpc_override": _runtime_secret_path(chain_settings, "rpc").is_file(),
        "runtime_wss_override": _runtime_secret_path(chain_settings, "wss").is_file(),
        "runtime_seed_override": _runtime_secret_path(chain_settings, "seed").is_file(),
    }


def schedule_process_restart() -> None:
    loop = asyncio.get_running_loop()
    loop.call_later(1.5, lambda: os.kill(os.getpid(), signal.SIGTERM))


def validate_deployment_settings(
    chain_settings: Settings,
    business: MiniAppSettings,
) -> None:
    business.validate_business_rules()
    if chain_settings.chain_enabled and business.demo_mode:
        raise ValueError("DEMO_MODE must be false when CHAIN_ENABLED is true")
    if chain_settings.environment == "production":
        if business.demo_mode:
            raise ValueError("DEMO_MODE is forbidden in production")
        if not business.miniapp_url.startswith("https://"):
            raise ValueError("MINIAPP_URL must use HTTPS in production")
        if not business.miniapp_origin.startswith("https://"):
            raise ValueError("MINIAPP_ORIGIN must use HTTPS in production")
        if "*" in business.trusted_host_list:
            raise ValueError("Wildcard TRUSTED_HOSTS is forbidden in production")


async def payout_loop(
    service: DailyPayoutService,
    stop_event: asyncio.Event,
    interval_seconds: int,
    runtime: RuntimeStatus,
) -> None:
    while not stop_event.is_set():
        try:
            await service.run_once()
            runtime.last_payout_tick = time.time()
            runtime.last_payout_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            runtime.last_payout_error = type(exc).__name__
            logger.exception("Payout worker failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(2, interval_seconds))
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(application: FastAPI):
    chain_settings = Settings()
    business = MiniAppSettings()
    validate_deployment_settings(chain_settings, business)

    repository = DeltaRepository(chain_settings.database_path, business)
    await repository.connect()
    runtime_overrides = await repository.get_runtime_settings()
    if runtime_overrides:
        apply_runtime_settings(business, chain_settings, runtime_overrides)
        business.validate_business_rules()
    # If V5 is installed while the legacy worker has already scheduled the
    # final profit day, add the missing principal payout without touching
    # deposits that were already completed before the upgrade.
    await repository.ensure_missing_principal_payouts()
    apply_runtime_secret_overrides(chain_settings)
    validate_chain_runtime_candidate(chain_settings)

    chain: EvmTokenClient | None = None
    chain_health: object | None = None
    if chain_settings.chain_enabled:
        chain = EvmTokenClient(chain_settings)
        chain_health = await chain.healthcheck()

    runtime = RuntimeStatus()
    safety_runtime = SafetyRuntime()
    payout_circuit = PayoutCircuitBreaker(safety_runtime)
    if not chain_settings.safety_monitor_enabled:
        payout_circuit.set_reasons([])
        safety_runtime.status = "disabled"
    stop_event = asyncio.Event()
    payout_service = DailyPayoutService(repository, chain_settings, chain, payout_circuit)
    tasks: list[asyncio.Task[object]] = []
    # Keep the payout worker alive even when payouts are temporarily disabled.
    # DailyPayoutService checks the runtime flag on every tick, so an admin can
    # disable and later re-enable payouts without restarting the container.
    tasks.append(
        asyncio.create_task(
            payout_loop(
                payout_service,
                stop_event,
                chain_settings.payout_interval_seconds,
                runtime,
            ),
            name="daily-payout-worker",
        )
    )

    if chain is not None:
        monitor = DepositMonitor(repository, chain_settings, chain, telemetry=safety_runtime)
        tasks.extend(
            [
                asyncio.create_task(
                    monitor.run_polling(stop_event),
                    name="deposit-http-monitor",
                ),
                asyncio.create_task(
                    monitor.run_websocket(stop_event),
                    name="deposit-wss-monitor",
                ),
            ]
        )

    bot_token = chain_settings.bot_token.get_secret_value()
    if business.run_bot_launcher:
        tasks.append(
            asyncio.create_task(
                run_launcher(
                    bot_token,
                    business.miniapp_url,
                    repository=repository,
                    admin_ids=chain_settings.admin_id_set,
                ),
                name="telegram-miniapp-launcher",
            )
        )
    if business.run_broadcast_worker:
        broadcaster = BroadcastService(repository, bot_token)
        tasks.append(
            asyncio.create_task(
                broadcaster.run(stop_event),
                name="telegram-broadcast-worker",
            )
        )

    notifier = UserNotificationService(repository, bot_token, business.miniapp_url)
    tasks.append(
        asyncio.create_task(
            notifier.run(stop_event),
            name="telegram-user-notification-worker",
        )
    )

    if chain_settings.safety_monitor_enabled:
        safety_monitor = SafetyMonitor(
            repository,
            chain_settings,
            chain,
            bot_token,
            safety_runtime,
            payout_circuit,
        )
        tasks.append(
            asyncio.create_task(
                safety_monitor.run(stop_event),
                name="gfort-safety-monitor",
            )
        )

    application.state.chain_settings = chain_settings
    application.state.business = business
    application.state.repository = repository
    application.state.chain = chain
    application.state.chain_health = chain_health
    application.state.runtime = runtime
    application.state.safety_runtime = safety_runtime
    application.state.payout_circuit = payout_circuit
    application.state.stop_event = stop_event
    application.state.tasks = tasks
    application.state.rate_limiter = SlidingWindowRateLimiter()
    try:
        yield
    finally:
        stop_event.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if chain is not None:
            await chain.close()
        await repository.close()


startup_settings = MiniAppSettings()
app = FastAPI(
    title="GFORT Mini App API",
    version="10.4-safety-mainnet",
    lifespan=lifespan,
    docs_url="/docs" if startup_settings.demo_mode else None,
    redoc_url=None,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=startup_settings.trusted_host_list,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[startup_settings.miniapp_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[
        "Content-Type",
        "Idempotency-Key",
        "X-Telegram-Init-Data",
        "X-Demo-Telegram-Id",
        "X-Request-Id",
    ],
    expose_headers=["X-Request-Id", "Retry-After"],
)


@app.middleware("http")
async def request_guard(request: Request, call_next):
    request_id_header = request.headers.get("x-request-id", "")
    request_id = (
        request_id_header
        if REQUEST_ID_RE.fullmatch(request_id_header)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id

    content_length = request.headers.get("content-length")
    if content_length:
        request_limit = (
            BROADCAST_MEDIA_MAX_BYTES * 2
            if request.url.path == "/api/admin/broadcast-media"
            else startup_settings.max_request_bytes
        )
        try:
            too_large = int(content_length) > request_limit
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body is too large"},
                headers={"X-Request-Id": request_id},
            )

    # Uvicorn normalizes request.url.scheme only for proxy addresses allowed by
    # FORWARDED_ALLOW_IPS. Reading X-Forwarded-Proto directly would let an
    # untrusted client bypass FORCE_HTTPS by spoofing the header.
    request_scheme = request.url.scheme
    client_host = request.client.host if request.client else ""
    local_healthcheck = client_host in {"127.0.0.1", "::1"}
    if startup_settings.force_https and request_scheme != "https" and not local_healthcheck:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "HTTPS is required"},
            headers={"X-Request-Id": request_id},
        )

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if request_scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _referrer_id_from_start_param(start_param: str | None) -> int | None:
    if start_param and start_param.startswith("ref_"):
        raw_referrer = start_param.removeprefix("ref_")
        if raw_referrer.isdigit():
            return int(raw_referrer)
    return None


async def _ensure_telegram_user(
    repository: DeltaRepository,
    telegram_user: TelegramUser,
) -> None:
    blocked = await repository.ensure_user(
        telegram_user.id,
        telegram_user.username,
        telegram_user.first_name,
        telegram_user.language_code,
        _referrer_id_from_start_param(telegram_user.start_param),
    )
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )


async def current_user(
    request: Request,
    response: Response,
    x_telegram_init_data: str | None = Header(default=None),
    x_gfort_telegram_context: str | None = Header(
        default=None,
        alias="X-GFORT-Telegram-Context",
    ),
    x_gfort_session: str | None = Header(default=None, alias="X-GFORT-Session"),
    x_demo_telegram_id: int | None = Header(default=None),
    delta_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthenticatedUser:
    """Authenticate GFORT without sharing identity between Telegram accounts.

    GFORT V10 uses a server-signed session token stored in Telegram's own
    per-user SecureStorage (CloudStorage is a compatibility fallback). That
    token is preferred inside Telegram because some Telegram clients reuse a
    WebView and its old initData while switching accounts. Browser cookies are
    never used in a native Telegram launch.
    """
    chain_settings: Settings = request.app.state.chain_settings
    business: MiniAppSettings = request.app.state.business
    repository: DeltaRepository = request.app.state.repository
    bot_token = chain_settings.bot_token.get_secret_value()
    telegram_user: TelegramUser | None = None
    init_data = (x_telegram_init_data or "").strip()
    client_session = (x_gfort_session or "").strip()
    native_context = bool(init_data) or str(x_gfort_telegram_context or "").strip().lower() in {
        "1", "true", "telegram", "native"
    }
    client_error: TelegramAuthError | None = None
    init_error: TelegramAuthError | None = None

    if business.demo_mode and x_demo_telegram_id is not None:
        telegram_user = TelegramUser(
            id=x_demo_telegram_id,
            username=f"demo_{x_demo_telegram_id}",
            first_name="Demo",
            language_code="ru",
        )
    else:
        # Telegram SecureStorage/CloudStorage is scoped to the currently logged
        # in Telegram user and this Mini App. A valid token read from there is
        # therefore the safest identity source when Telegram reuses WebViews.
        if client_session:
            try:
                telegram_user = validate_web_session(client_session, bot_token)
            except TelegramAuthError as exc:
                client_error = exc

        # Fresh signed initData remains the normal bootstrap path. Keep an age
        # limit here; after bootstrap the per-user Telegram session is used.
        if telegram_user is None and init_data:
            try:
                telegram_user = validate_init_data(
                    init_data,
                    bot_token,
                    max_age_seconds=business.telegram_init_data_ttl_seconds,
                )
            except TelegramAuthError as exc:
                init_error = exc

        if telegram_user is None and native_context:
            detail = str(init_error or client_error or "Telegram authorization is unavailable")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            )

        if telegram_user is None and delta_session:
            try:
                telegram_user = validate_web_session(delta_session, bot_token)
            except TelegramAuthError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                ) from exc

        if telegram_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telegram authorization is unavailable",
            )

    await _ensure_telegram_user(repository, telegram_user)

    if native_context and not business.demo_mode:
        # Domain cookies are shared by some Telegram clients across accounts.
        # They are intentionally removed from native Telegram requests.
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=business.force_https,
            httponly=True,
            samesite="lax",
        )

    dynamic_admin = await repository.is_granted_admin(telegram_user.id)
    return AuthenticatedUser(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        is_admin=telegram_user.id in chain_settings.admin_id_set or dynamic_admin,
    )


async def admin_user(
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def enforce_mutation_limit(
    request: Request,
    user: AuthenticatedUser,
    action: str,
) -> None:
    settings: MiniAppSettings = request.app.state.business
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    retry_after = await limiter.check(
        f"{user.telegram_id}:{action}",
        settings.mutation_rate_limit,
        settings.mutation_rate_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    return {
        "status": "ok",
        "version": app.version,
        "environment": chain_settings.environment,
    }


@app.get("/ready")
async def ready(request: Request):
    repository: DeltaRepository = request.app.state.repository
    tasks: list[asyncio.Task[object]] = request.app.state.tasks
    database_ok = await repository.ping()
    failed_tasks = [task.get_name() for task in tasks if task.done() and not task.cancelled()]
    ready_now = database_ok and not failed_tasks
    safety_runtime: SafetyRuntime = request.app.state.safety_runtime
    payload = {
        "status": "ready" if ready_now else "not_ready",
        "database": database_ok,
        "failed_tasks": failed_tasks,
        "safety": {
            "status": safety_runtime.status,
            "circuit_open": safety_runtime.circuit_open,
            "active_alerts": list(safety_runtime.active_alerts),
        },
    }
    if ready_now:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.post("/api/session/exchange")
async def exchange_bot_login(
    payload: SessionExchangeRequest,
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    x_gfort_telegram_context: str | None = Header(
        default=None,
        alias="X-GFORT-Telegram-Context",
    ),
    x_gfort_session: str | None = Header(default=None, alias="X-GFORT-Session"),
) -> JSONResponse:
    chain_settings: Settings = request.app.state.chain_settings
    business: MiniAppSettings = request.app.state.business
    repository: DeltaRepository = request.app.state.repository
    bot_token = chain_settings.bot_token.get_secret_value()
    init_data = (x_telegram_init_data or "").strip()
    client_session = (x_gfort_session or "").strip()
    native_context = bool(init_data) or str(x_gfort_telegram_context or "").strip().lower() in {
        "1", "true", "telegram", "native"
    }

    # /start tokens are one-time, random and live for only ten minutes. They
    # are the recovery path for Telegram clients whose cached WebView does not
    # expose usable initData on the first V10 launch.
    token_user = await repository.consume_web_login_token(payload.token)
    if token_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bot login link is invalid or expired",
        )

    stored_user: TelegramUser | None = None
    if client_session:
        try:
            stored_user = validate_web_session(client_session, bot_token)
        except TelegramAuthError:
            stored_user = None
        if stored_user is not None and stored_user.id != token_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bot login link belongs to another Telegram account",
            )

    signed_user: TelegramUser | None = None
    if init_data:
        try:
            signed_user = validate_init_data(
                init_data,
                bot_token,
                max_age_seconds=business.telegram_init_data_ttl_seconds,
            )
        except TelegramAuthError:
            # A valid one-time /start token is intentionally allowed to repair
            # cached/missing initData. Do not fail the recovery path here.
            signed_user = None
        if signed_user is not None and signed_user.id != token_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bot login link belongs to another Telegram account",
            )

    profile_user = signed_user or stored_user or token_user
    telegram_user = TelegramUser(
        id=token_user.id,
        username=profile_user.username or token_user.username,
        first_name=profile_user.first_name or token_user.first_name,
        language_code=profile_user.language_code or token_user.language_code,
        start_param=token_user.start_param,
    )
    await _ensure_telegram_user(repository, telegram_user)

    if native_context:
        response = JSONResponse(
            content={
                "status": "ok",
                "mode": "telegram",
                "session_token": issue_web_session(
                    telegram_user,
                    bot_token,
                    CLIENT_SESSION_TTL_SECONDS,
                ),
                "expires_in": CLIENT_SESSION_TTL_SECONDS,
            }
        )
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=business.force_https,
            httponly=True,
            samesite="lax",
        )
        return response

    # External-browser one-time links keep a normal HttpOnly cookie.
    response = JSONResponse(
        content={
            "status": "ok",
            "mode": "external",
            "expires_in": business.telegram_session_ttl_seconds,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issue_web_session(
            telegram_user,
            bot_token,
            business.telegram_session_ttl_seconds,
        ),
        max_age=business.telegram_session_ttl_seconds,
        expires=business.telegram_session_ttl_seconds,
        path="/",
        secure=business.force_https,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/bootstrap")
async def bootstrap(
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    result = await repository.bootstrap(user.telegram_id)
    result["auth"] = user.model_dump()
    result["auth_session_token"] = issue_web_session(
        TelegramUser(
            id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            language_code=None,
        ),
        chain_settings.bot_token.get_secret_value(),
        CLIENT_SESSION_TTL_SECONDS,
    )
    result["auth_session_expires_in"] = CLIENT_SESSION_TTL_SECONDS
    result["server_time"] = int(time.time())
    result["mode"] = {
        "environment": chain_settings.environment,
        "demo": business.demo_mode,
        "mainnet": chain_settings.chain_enabled and chain_settings.chain_id == 56,
        "web_only": not chain_settings.chain_enabled,
    }
    result["terms"] = {
        "daily_profit_bps": business.daily_profit_bps,
        "payout_days": business.payout_days,
        "deposit_min_usdt": business.deposit_min_usdt,
        "deposit_max_usdt": business.deposit_max_usdt,
        "referral_level_bps": business.referral_level_bps,
        "referral_personal_thresholds_usdt": business.referral_personal_thresholds_usdt,
        "referral_line_thresholds_usdt": business.referral_line_thresholds_usdt,
    }
    result["chain"] = {
        "enabled": chain_settings.chain_enabled,
        "deposits_enabled": chain_settings.deposits_enabled,
        "payouts_enabled": chain_settings.payouts_enabled,
        "chain_id": chain_settings.chain_id,
        "token_symbol": chain_settings.token_symbol,
        "treasury_address": chain_settings.treasury_address,
        "simulate_payouts": chain_settings.simulate_payouts,
        "explorer_tx_url": chain_settings.block_explorer_tx_url,
        "confirmation_blocks": chain_settings.confirmation_blocks,
    }
    bot_username = business.bot_username.lstrip("@")
    result["referral_link"] = (
        f"https://t.me/{bot_username}?start=ref_{user.telegram_id}"
    )
    result["support_url"] = chain_settings.support_url
    result["chat_url"] = chain_settings.chat_url
    return result


@app.get("/api/notifications")
async def notifications(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    category: str | None = Query(default=None),
    after_id: int | None = Query(default=None, ge=1),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.list_notifications(
        user.telegram_id,
        limit=limit,
        category=category,
        after_id=after_id,
    )


@app.post("/api/notifications/{notification_id}/read")
async def read_notification(
    notification_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "notification-read")
    repository: DeltaRepository = request.app.state.repository
    return {"read": await repository.mark_notification_read(user.telegram_id, notification_id)}


@app.post("/api/notifications/read-all")
async def read_all_notifications(
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "notification-read-all")
    repository: DeltaRepository = request.app.state.repository
    return {"updated": await repository.mark_all_notifications_read(user.telegram_id)}


@app.get("/api/team")
async def team(
    request: Request,
    today_start: int | None = Query(default=None, ge=0),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.team(user.telegram_id, today_start=today_start)


@app.post("/api/referrals/withdraw")
async def withdraw_referral_rewards(
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-withdrawal")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    chain_settings: Settings = request.app.state.chain_settings
    if not (chain_settings.chain_enabled and chain_settings.payouts_enabled):
        raise HTTPException(status_code=503, detail="Payouts are temporarily disabled")
    repository: DeltaRepository = request.app.state.repository
    try:
        payout = await repository.request_referral_withdrawal(
            user.telegram_id,
            idempotency_key,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "payout_id": int(payout["id"]),
        "amount_minor": int(payout["amount_minor"]),
        "address": str(payout["address"]),
        "status": str(payout["status"]),
        "reused": bool(payout.get("reused", False)),
    }


@app.post("/api/wallet")
async def set_wallet(
    payload: WalletRequest,
    request: Request,
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, str]:
    await enforce_mutation_limit(request, user, "wallet")
    chain_settings: Settings = request.app.state.chain_settings
    if not chain_settings.chain_enabled:
        raise HTTPException(
            status_code=503,
            detail="Wallet configuration is disabled in web-only mode",
        )
    if not Web3.is_address(payload.address):
        raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
    address = Web3.to_checksum_address(payload.address)
    repository: DeltaRepository = request.app.state.repository
    try:
        await repository.set_wallet(user.telegram_id, address)
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"address": address}


@app.post("/api/deposits/invoice")
async def create_invoice(
    payload: InvoiceRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(current_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "invoice")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")
    repository: DeltaRepository = request.app.state.repository
    chain_settings: Settings = request.app.state.chain_settings
    if not (
        chain_settings.chain_enabled
        and chain_settings.deposits_enabled
        and chain_settings.payouts_enabled
    ):
        raise HTTPException(
            status_code=503,
            detail="Deposits are temporarily disabled",
        )
    if not chain_settings.treasury_address:
        raise HTTPException(status_code=503, detail="Treasury wallet is not configured")
    try:
        invoice = await repository.create_invoice(
            user.telegram_id,
            usdt_to_minor(payload.amount),
            idempotency_key,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "invoice_id": invoice["invoice_id"],
        "exact_amount": minor_to_text(int(invoice["exact_minor"]), trim=False),
        "expires_at": invoice["expires_at"],
        "reused": bool(invoice.get("reused", False)),
        "treasury_address": chain_settings.treasury_address,
        "token_symbol": chain_settings.token_symbol,
        "chain_id": chain_settings.chain_id,
    }


@app.get("/api/admin/summary")
async def admin_summary(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_summary()


@app.get("/api/admin/users")
async def admin_users(
    request: Request,
    query: str = Query(default="", max_length=64),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_users(query)


@app.get("/api/admin/users/{telegram_id}")
async def admin_user_detail(
    telegram_id: int,
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    repository: DeltaRepository = request.app.state.repository
    result = await repository.admin_user_detail(telegram_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@app.post("/api/admin/users/{telegram_id}/block")
async def admin_block_user(
    telegram_id: int,
    payload: BlockRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "block-user")
    if telegram_id == user.telegram_id and payload.blocked:
        raise HTTPException(status_code=409, detail="Administrator cannot block itself")
    repository: DeltaRepository = request.app.state.repository
    changed = await repository.set_user_blocked(telegram_id, payload.blocked)
    if not changed:
        raise HTTPException(status_code=404, detail="User not found")
    return {"blocked": payload.blocked}


@app.post("/api/admin/users/{telegram_id}/balance")
async def admin_set_user_balance(
    telegram_id: int,
    payload: AdminUserBalanceRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-balance")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.set_user_balance(
            telegram_id,
            usdt_to_minor(payload.balance_usdt),
            user.telegram_id,
            payload.reason,
        )
    except RepositoryError as exc:
        code = 404 if str(exc) == "User not found" else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {
        **result,
        "balance_usdt": minor_to_text(int(result["new_balance_minor"]), trim=False),
    }


@app.post("/api/admin/users/{telegram_id}/wallet")
async def admin_set_user_wallet(
    telegram_id: int,
    payload: AdminUserWalletRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-wallet")
    raw = (payload.address or "").strip()
    address: str | None = None
    if raw:
        if not Web3.is_address(raw):
            raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
        address = Web3.to_checksum_address(raw)
    repository: DeltaRepository = request.app.state.repository
    if not await repository.admin_set_user_wallet(telegram_id, address, user.telegram_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"address": address}


@app.post("/api/admin/users/{telegram_id}/referrer")
async def admin_set_user_referrer(
    telegram_id: int,
    payload: AdminUserReferrerRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "user-referrer")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_set_user_referrer(
            telegram_id,
            payload.identifier,
            user.telegram_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif detail == "Referrer not found":
            code = 404
        elif "cycle" in detail.lower() or "own referrer" in detail.lower():
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return result


@app.post("/api/admin/users/{telegram_id}/referral-balance")
async def admin_set_referral_balance(
    telegram_id: int,
    payload: AdminReferralBalanceRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-balance")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_set_referral_balance(
            telegram_id,
            usdt_to_minor(payload.balance_usdt),
            user.telegram_id,
            payload.reason,
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=404 if str(exc) == "User not found" else 422,
            detail=str(exc),
        ) from exc
    return {
        **result,
        "balance_usdt": minor_to_text(int(result["new_balance_minor"]), trim=False),
    }


@app.post("/api/admin/users/{telegram_id}/referral-level")
async def admin_set_referral_level(
    telegram_id: int,
    payload: AdminReferralLevelRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "referral-level")
    repository: DeltaRepository = request.app.state.repository
    try:
        return await repository.admin_set_referral_level(
            telegram_id,
            payload.unlocked_level,
            user.telegram_id,
            payload.reason,
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=404 if str(exc) == "User not found" else 422,
            detail=str(exc),
        ) from exc


@app.post("/api/admin/users/{telegram_id}/investments")
async def admin_open_investment(
    telegram_id: int,
    payload: AdminOpenInvestmentRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "open-investment")
    repository: DeltaRepository = request.app.state.repository
    try:
        result = await repository.admin_open_investment(
            telegram_id,
            usdt_to_minor(payload.amount_usdt),
            user.telegram_id,
            payload.reason,
            payload.operation_id,
        )
    except RepositoryError as exc:
        detail = str(exc)
        if detail == "User not found":
            code = 404
        elif detail == "Account is blocked":
            code = 409
        else:
            code = 422
        raise HTTPException(status_code=code, detail=detail) from exc
    return {
        **result,
        "amount_usdt": minor_to_text(int(result["principal_minor"]), trim=False),
    }


@app.get("/api/admin/admins")
async def admin_admins(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    chain_settings: Settings = request.app.state.chain_settings
    return await repository.admin_admins(chain_settings.admin_id_set)


@app.post("/api/admin/admins")
async def add_admin(
    payload: AdminGrantRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "grant-admin")
    repository: DeltaRepository = request.app.state.repository
    chain_settings: Settings = request.app.state.chain_settings
    try:
        result = await repository.grant_admin(payload.identifier, user.telegram_id)
    except RepositoryError as exc:
        if str(exc) == "User not found":
            raise HTTPException(status_code=404, detail="User not found") from exc
        raise HTTPException(status_code=422, detail="Invalid administrator identifier") from exc
    if int(result["telegram_id"]) in chain_settings.admin_id_set:
        result["source"] = "bootstrap"
        result["protected"] = True
    return result


@app.delete("/api/admin/admins/{telegram_id}")
async def remove_admin(
    telegram_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "revoke-admin")
    chain_settings: Settings = request.app.state.chain_settings
    if telegram_id in chain_settings.admin_id_set:
        raise HTTPException(status_code=409, detail="Bootstrap administrator cannot be removed")
    if telegram_id == user.telegram_id:
        raise HTTPException(status_code=409, detail="Administrator cannot remove itself")
    repository: DeltaRepository = request.app.state.repository
    removed = await repository.revoke_admin(telegram_id, user.telegram_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Administrator grant not found")
    return {"removed": True}


@app.get("/api/admin/deposits")
async def admin_deposits(
    request: Request,
    deposit_status: Literal["active", "completed", "paused", "failed"] | None = Query(
        default=None,
        alias="status",
    ),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_deposits(deposit_status)


@app.get("/api/admin/operations")
async def admin_operations(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_operations()


@app.post("/api/admin/payouts/{payout_id}/retry")
async def retry_payout(
    payout_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, bool]:
    await enforce_mutation_limit(request, user, "retry-payout")
    repository: DeltaRepository = request.app.state.repository
    return {"retried": await repository.retry_payout(payout_id)}


@app.get("/api/admin/broadcasts")
async def admin_broadcasts(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_broadcasts()


@app.post("/api/admin/broadcast-media")
async def upload_broadcast_media(
    payload: BroadcastMediaUploadRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "broadcast-media")
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid image encoding") from exc
    if not raw or len(raw) > BROADCAST_MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    if payload.mime_type == "image/jpeg":
        if not raw.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=422, detail="Invalid JPEG image")
        extension = ".jpg"
    else:
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=422, detail="Invalid PNG image")
        extension = ".png"
    chain_settings: Settings = request.app.state.chain_settings
    media_dir = Path(chain_settings.database_path).parent / "broadcast_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    try:
        media_dir.chmod(0o700)
    except OSError:
        pass
    media_id = f"{uuid.uuid4().hex}{extension}"
    path = media_dir / media_id
    path.write_bytes(raw)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"media_id": media_id, "size": len(raw), "mime_type": payload.mime_type}


@app.post("/api/admin/broadcasts")
async def create_broadcast(
    payload: BroadcastRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, int | str]:
    await enforce_mutation_limit(request, user, "broadcast")
    message = sanitize_telegram_html(payload.message)
    buttons = validate_broadcast_buttons(payload.buttons)
    media_path: str | None = None
    if payload.media_id:
        if not BROADCAST_MEDIA_ID_RE.fullmatch(payload.media_id):
            raise HTTPException(status_code=422, detail="Invalid broadcast image id")
        chain_settings: Settings = request.app.state.chain_settings
        candidate = Path(chain_settings.database_path).parent / "broadcast_media" / payload.media_id
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Broadcast image not found")
        media_path = str(candidate)
    if not message and not media_path:
        raise HTTPException(status_code=422, detail="Broadcast message or image is required")
    repository: DeltaRepository = request.app.state.repository
    return await repository.create_broadcast(
        user.telegram_id,
        message,
        payload.audience,
        parse_mode="HTML",
        media_path=media_path,
        buttons=buttons,
    )


@app.get("/api/admin/treasury")
async def admin_treasury(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    chain: EvmTokenClient | None = request.app.state.chain
    if chain is None or not chain_settings.chain_enabled:
        return {
            "enabled": False,
            "chain_id": chain_settings.chain_id,
            "address": chain_settings.treasury_address,
            "token_symbol": chain_settings.token_symbol,
            "payouts_enabled": chain_settings.payouts_enabled,
            "simulate_payouts": chain_settings.simulate_payouts,
            "explorer_tx_url": chain_settings.block_explorer_tx_url,
        }
    token_atomic, native_wei = await asyncio.gather(
        chain.token_balance(chain_settings.treasury_address),
        chain.native_balance(chain_settings.treasury_address),
    )
    token_value = Decimal(token_atomic) / (Decimal(10) ** chain_settings.token_decimals)
    native_value = Decimal(native_wei) / (Decimal(10) ** 18)
    return {
        "enabled": True,
        "chain_id": chain_settings.chain_id,
        "address": chain_settings.treasury_address,
        "token_symbol": chain_settings.token_symbol,
        "token_balance": format(token_value, "f"),
        "native_balance": format(native_value, "f"),
        "payouts_enabled": chain_settings.payouts_enabled,
        "simulate_payouts": chain_settings.simulate_payouts,
        "explorer_tx_url": chain_settings.block_explorer_tx_url,
    }


@app.get("/api/admin/treasury/test-payouts")
async def admin_test_payouts(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_test_payouts()


@app.post("/api/admin/treasury/test-payout")
async def create_admin_test_payout(
    payload: AdminTestPayoutRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "admin-test-payout")
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")

    chain_settings: Settings = request.app.state.chain_settings
    chain: EvmTokenClient | None = request.app.state.chain
    if not chain_settings.payouts_enabled:
        raise HTTPException(status_code=503, detail="Payouts are temporarily disabled")
    if chain is None or not chain_settings.chain_enabled or chain_settings.simulate_payouts:
        raise HTTPException(status_code=503, detail="Real payouts are not enabled")
    if not Web3.is_address(payload.address):
        raise HTTPException(status_code=422, detail="Invalid BNB Chain address")
    address = Web3.to_checksum_address(payload.address)
    if address.lower() == chain_settings.treasury_address.lower():
        raise HTTPException(status_code=422, detail="Destination must differ from treasury")

    try:
        amount_minor = usdt_to_minor(payload.amount)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid payout amount") from exc
    if amount_minor < MINOR_FACTOR:
        raise HTTPException(status_code=422, detail="Minimum admin test payout is 1 USDT")

    native_wei, token_atomic = await chain.signer_balances()
    required_atomic = minor_to_atomic(amount_minor, chain_settings.token_decimals)
    if token_atomic < required_atomic:
        raise HTTPException(status_code=409, detail="Insufficient treasury USDT balance")
    if native_wei <= 0:
        raise HTTPException(status_code=409, detail="Treasury has no BNB for gas")

    repository: DeltaRepository = request.app.state.repository
    try:
        payout = await repository.request_admin_test_payout(
            user.telegram_id,
            address,
            amount_minor,
            idempotency_key,
        )
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "payout_id": int(payout["id"]),
        "amount_minor": int(payout["amount_minor"]),
        "address": str(payout["address"]),
        "status": str(payout["status"]),
        "reused": bool(payout.get("reused", False)),
        "real": True,
    }


@app.get("/api/admin/settings")
async def admin_runtime_settings(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    return runtime_settings_snapshot(request.app.state.business, request.app.state.chain_settings)


@app.post("/api/admin/settings")
async def update_admin_runtime_settings(
    payload: RuntimeSettingsRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "runtime-settings")
    validate_runtime_settings_payload(payload)
    values = payload.model_dump()
    repository: DeltaRepository = request.app.state.repository
    try:
        await repository.set_runtime_settings(values, user.telegram_id)
    except RepositoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    apply_runtime_settings(business, chain_settings, values)
    business.validate_business_rules()
    return runtime_settings_snapshot(business, chain_settings)


@app.get("/api/admin/terms")
async def admin_terms(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    business: MiniAppSettings = request.app.state.business
    chain_settings: Settings = request.app.state.chain_settings
    return {
        "daily_profit_bps": business.daily_profit_bps,
        "payout_days": business.payout_days,
        "deposit_min_usdt": business.deposit_min_usdt,
        "deposit_max_usdt": business.deposit_max_usdt,
        "referral_level_bps": business.referral_level_bps,
        "referral_personal_thresholds_usdt": business.referral_personal_thresholds_usdt,
        "referral_line_thresholds_usdt": business.referral_line_thresholds_usdt,
        "chain_id": chain_settings.chain_id,
        "token_symbol": chain_settings.token_symbol,
        "treasury_address": chain_settings.treasury_address,
        "confirmation_blocks": chain_settings.confirmation_blocks,
        "deposit_scan_interval_seconds": chain_settings.deposit_scan_interval_seconds,
    }


@app.get("/api/admin/audit")
async def admin_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    _user: AuthenticatedUser = Depends(admin_user),
) -> list[dict[str, object]]:
    repository: DeltaRepository = request.app.state.repository
    return await repository.admin_audit(limit)


@app.get("/api/admin/chain-config")
async def admin_chain_config(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    return chain_runtime_snapshot(request.app.state.chain_settings)


@app.post("/api/admin/chain-config")
async def update_admin_chain_config(
    payload: ChainRuntimeConfigRequest,
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "chain-config")
    current: Settings = request.app.state.chain_settings
    candidate = current.model_copy(deep=True)

    if payload.mode == "production":
        candidate.environment = "production"
        candidate.chain_enabled = True
        candidate.simulate_payouts = False
        candidate.chain_id = 56
    elif payload.mode == "testnet":
        candidate.environment = "testnet"
        candidate.chain_enabled = True
        candidate.simulate_payouts = False
        candidate.chain_id = 97
    else:
        candidate.chain_enabled = False
        candidate.simulate_payouts = True

    candidate.token_contract = Web3.to_checksum_address(payload.token_contract) if Web3.is_address(payload.token_contract) else payload.token_contract
    candidate.scan_start_block = int(payload.scan_start_block)

    rpc = (payload.rpc_url or "").strip()
    wss = (payload.wss_url or "").strip()
    seed = (payload.seed_phrase or "").strip()
    if rpc:
        candidate.bsc_rpc_url = rpc
    if wss:
        candidate.bsc_wss_url = wss
    if seed:
        candidate.payout_seed_phrase = SecretStr(seed)
        candidate.payout_private_key = None
        candidate.payout_keystore_path = None
        candidate.payout_keystore_password = None

    validate_chain_runtime_candidate(candidate)

    rpc_health: dict[str, object] | None = None
    wss_health: dict[str, object] | None = None
    if candidate.chain_enabled:
        client = EvmTokenClient(candidate)
        try:
            http_result = await client.healthcheck()
            ws_result = await client.websocket_healthcheck()
            rpc_health = {"chain_id": http_result.chain_id, "block_number": http_result.block_number}
            wss_health = {"chain_id": ws_result.chain_id, "block_number": ws_result.block_number, "subscription_ok": ws_result.subscription_ok}
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"New blockchain configuration failed health check: {client.safe_error(exc)}") from exc
        finally:
            await client.close()

    nonsecret = {
        "environment": candidate.environment,
        "chain_enabled": bool(candidate.chain_enabled),
        "simulate_payouts": bool(candidate.simulate_payouts),
        "chain_id": int(candidate.chain_id),
        "token_contract": candidate.token_contract,
        "treasury_address": candidate.treasury_address,
        "scan_start_block": int(candidate.scan_start_block),
        "runtime_rpc_override": bool(rpc) or _runtime_secret_path(current, "rpc").is_file(),
        "runtime_wss_override": bool(wss) or _runtime_secret_path(current, "wss").is_file(),
        "runtime_seed_override": bool(seed) or _runtime_secret_path(current, "seed").is_file(),
    }
    repository: DeltaRepository = request.app.state.repository
    await repository.set_runtime_settings(nonsecret, user.telegram_id)
    if rpc:
        _write_runtime_secret(current, "rpc", rpc)
    if wss:
        _write_runtime_secret(current, "wss", wss)
    if seed:
        _write_runtime_secret(current, "seed", seed)

    schedule_process_restart()
    return {
        "saved": True,
        "restart_scheduled": True,
        "mode": payload.mode,
        "treasury_address": candidate.treasury_address,
        "rpc_health": rpc_health,
        "wss_health": wss_health,
    }


@app.get("/api/admin/safety")
async def admin_safety(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    runtime: SafetyRuntime = request.app.state.safety_runtime
    repository: DeltaRepository = request.app.state.repository
    result = runtime.snapshot()
    result["queue"] = await repository.payout_safety_metrics()
    return result


@app.get("/api/admin/system")
async def admin_system(
    request: Request,
    _user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    chain_settings: Settings = request.app.state.chain_settings
    runtime: RuntimeStatus = request.app.state.runtime
    tasks: list[asyncio.Task[object]] = request.app.state.tasks
    signing_configured = bool(
        chain_settings.payout_seed_phrase
        or chain_settings.payout_private_key
        or (
            chain_settings.payout_keystore_path
            and chain_settings.payout_keystore_password
        )
    )
    safety_runtime: SafetyRuntime = request.app.state.safety_runtime
    return {
        "uptime_seconds": int(time.time() - runtime.started_at),
        "last_payout_tick": runtime.last_payout_tick,
        "last_payout_error": runtime.last_payout_error,
        "chain_enabled": chain_settings.chain_enabled,
        "chain_id": chain_settings.chain_id,
        "simulate_payouts": chain_settings.simulate_payouts,
        "safety": safety_runtime.snapshot(),
        "tasks": {
            task.get_name(): "stopped" if task.done() else "running"
            for task in tasks
        },
        "blockchain_configuration": {
            "rpc_configured": bool(chain_settings.bsc_rpc_url),
            "wss_configured": bool(chain_settings.bsc_wss_url),
            "token_contract_configured": bool(chain_settings.token_contract),
            "treasury_address_configured": bool(chain_settings.treasury_address),
            "signing_configured": signing_configured,
            "activation_scope": "bsc_mainnet" if chain_settings.chain_id == 56 else "bsc_testnet",
            "restart_required": True,
        },
    }
