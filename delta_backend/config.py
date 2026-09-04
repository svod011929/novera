import re
from decimal import Decimal
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from eth_account import Account

from .enums import ReferralPayoutMode

SUPPORTED_LOCALES = ("ru", "en", "it", "es", "uk", "ky", "uz")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
MAX_SECRET_FILE_BYTES = 65_536


def _read_secret_file(path: Path, setting_name: str) -> str:
    try:
        if not path.is_file():
            raise ValueError(f"{setting_name}_FILE не является обычным файлом")
        if path.stat().st_size > MAX_SECRET_FILE_BYTES:
            raise ValueError(f"{setting_name}_FILE слишком большой")
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"не удалось прочитать {setting_name}_FILE") from exc
    if not value:
        raise ValueError(f"{setting_name}_FILE пуст")
    return value


def _resolve_text_secret(
    setting_name: str,
    direct_value: str,
    file_path: Path | None,
) -> str:
    direct_value = direct_value.strip()
    if file_path is None:
        return direct_value
    if direct_value:
        raise ValueError(
            f"укажите только один источник: {setting_name} или {setting_name}_FILE"
        )
    return _read_secret_file(file_path, setting_name)


def _resolve_secret_str(
    setting_name: str,
    direct_value: SecretStr | None,
    file_path: Path | None,
) -> SecretStr | None:
    raw_value = direct_value.get_secret_value().strip() if direct_value else ""
    resolved = _resolve_text_secret(setting_name, raw_value, file_path)
    return SecretStr(resolved) if resolved else None


class Settings(BaseSettings):
    # Используем абсолютный путь, чтобы RubyHost/Pterodactyl мог запускать бота из любой рабочей папки.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Empty dotenv values such as SEED_PHRASE_FILE= must stay unset.
        # Without this, pydantic converts an empty Path value to Path("."),
        # which then fails the regular-file secret validation.
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    bot_token: SecretStr = SecretStr("")
    bot_token_file: Path | None = None
    admin_ids: str = ""
    log_channel_id: int | None = None
    support_url: str = "https://t.me/your_support"
    chat_url: str = "https://t.me/your_chat"

    environment: str = "development"
    database_path: Path = Path("data/bot.sqlite3")
    default_locale: str = "ru"
    referral_payout_mode: ReferralPayoutMode = ReferralPayoutMode.BALANCE
    invoice_ttl_minutes: int = 30
    deposit_min_usdt: Decimal = Decimal("1")
    deposit_max_usdt: Decimal = Decimal("100000")

    deposits_enabled: bool = True
    investments_enabled: bool = True
    payouts_enabled: bool = True
    referral_enabled: bool = True

    chain_enabled: bool = False
    simulate_payouts: bool = True

    # RPC-адреса не имеют значений по умолчанию в исходном коде. Настраивайте их только в .env.
    bsc_rpc_url: str = ""
    bsc_rpc_url_file: Path | None = None
    bsc_rpc_fallback_url: str = ""
    bsc_rpc_fallback_url_file: Path | None = None
    bsc_wss_url: str = ""
    bsc_wss_url_file: Path | None = None
    chain_id: int = Field(
        default=56,
        validation_alias=AliasChoices("BSC_CHAIN_ID", "CHAIN_ID"),
    )
    bsc_rpc_timeout_seconds: float = 20.0
    bsc_wss_open_timeout_seconds: float = 15.0
    bsc_wss_rpc_timeout_seconds: float = 15.0
    bsc_wss_ping_interval_seconds: float = 20.0
    bsc_wss_ping_timeout_seconds: float = 20.0

    token_contract: str = ""
    token_symbol: str = "USDT"
    token_decimals: int = 18
    treasury_address: str = ""
    payout_seed_phrase: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SEED_PHRASE", "PAYOUT_SEED_PHRASE"),
    )
    payout_seed_phrase_file: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("SEED_PHRASE_FILE", "PAYOUT_SEED_PHRASE_FILE"),
    )
    seed_account_path: str = Field(
        default="m/44'/60'/0'/0/0",
        validation_alias=AliasChoices("SEED_ACCOUNT_PATH", "PAYOUT_ACCOUNT_PATH"),
    )
    payout_private_key: SecretStr | None = None
    payout_private_key_file: Path | None = None
    payout_keystore_path: Path | None = None
    payout_keystore_password: SecretStr | None = None
    payout_keystore_password_file: Path | None = None
    scan_start_block: int = 0
    confirmation_blocks: int = 12
    scan_block_chunk: int = 1500
    deposit_scan_interval_seconds: int = 15
    payout_interval_seconds: int = 10
    block_explorer_tx_url: str = "https://bscscan.com/tx/{tx_hash}"
    minimum_native_balance_wei: int = 1_000_000_000_000_000
    minimum_token_balance_usdt: Decimal = Decimal("1")

    # GFORT V10.4 production safety layer. These settings do not change the
    # accounting rules; they only govern monitoring, backups and payout signing.
    safety_monitor_enabled: bool = True
    safety_check_interval_seconds: int = 30
    safety_startup_grace_seconds: int = 180
    safety_min_native_balance_wei: int = 1_000_000_000_000_000
    safety_payout_stuck_seconds: int = 900
    safety_wss_stale_seconds: int = 180
    safety_http_scan_stale_seconds: int = 300
    safety_integrity_interval_seconds: int = 3600
    safety_backup_interval_seconds: int = 3600
    safety_backup_stale_seconds: int = 10800
    safety_backup_retention_count: int = 72

    live_mode_ack: bool = False
    security_audit_ack: bool = False
    legal_review_ack: bool = False

    @property
    def admin_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.admin_ids.split(","):
            item = item.strip()
            if item:
                result.add(int(item))
        return result

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        self.bot_token = _resolve_secret_str(
            "BOT_TOKEN", self.bot_token, self.bot_token_file
        ) or SecretStr("")
        self.bsc_rpc_url = _resolve_text_secret(
            "BSC_RPC_URL", self.bsc_rpc_url, self.bsc_rpc_url_file
        )
        self.bsc_rpc_fallback_url = _resolve_text_secret(
            "BSC_RPC_FALLBACK_URL",
            self.bsc_rpc_fallback_url,
            self.bsc_rpc_fallback_url_file,
        )
        self.bsc_wss_url = _resolve_text_secret(
            "BSC_WSS_URL", self.bsc_wss_url, self.bsc_wss_url_file
        )
        self.payout_seed_phrase = _resolve_secret_str(
            "SEED_PHRASE", self.payout_seed_phrase, self.payout_seed_phrase_file
        )
        self.payout_private_key = _resolve_secret_str(
            "PAYOUT_PRIVATE_KEY",
            self.payout_private_key,
            self.payout_private_key_file,
        )
        self.payout_keystore_password = _resolve_secret_str(
            "PAYOUT_KEYSTORE_PASSWORD",
            self.payout_keystore_password,
            self.payout_keystore_password_file,
        )

        if not self.bot_token.get_secret_value().strip():
            raise ValueError("BOT_TOKEN или BOT_TOKEN_FILE не должен быть пустым")
        self.environment = self.environment.strip().lower()
        if self.environment not in {"development", "testnet", "production"}:
            raise ValueError("ENVIRONMENT должен быть development, testnet или production")
        if self.default_locale not in SUPPORTED_LOCALES:
            raise ValueError(f"DEFAULT_LOCALE должен быть одним из: {SUPPORTED_LOCALES}")
        if not 6 <= self.token_decimals <= 18:
            raise ValueError("TOKEN_DECIMALS должен быть в диапазоне от 6 до 18")
        if self.deposit_min_usdt <= 0 or self.deposit_max_usdt < self.deposit_min_usdt:
            raise ValueError("неверные лимиты депозита: проверьте DEPOSIT_MIN_USDT и DEPOSIT_MAX_USDT")
        if self.bsc_rpc_timeout_seconds <= 0:
            raise ValueError("BSC_RPC_TIMEOUT_SECONDS должен быть больше 0")
        if self.bsc_wss_open_timeout_seconds <= 0 or self.bsc_wss_rpc_timeout_seconds <= 0:
            raise ValueError("таймауты BSC WebSocket должны быть больше 0")
        if self.bsc_wss_ping_interval_seconds <= 0 or self.bsc_wss_ping_timeout_seconds <= 0:
            raise ValueError("настройки ping BSC WebSocket должны быть больше 0")
        if self.minimum_native_balance_wei < 0 or self.minimum_token_balance_usdt < 0:
            raise ValueError("минимальные балансы кошелька не могут быть отрицательными")
        if self.safety_min_native_balance_wei < 0:
            raise ValueError("SAFETY_MIN_NATIVE_BALANCE_WEI не может быть отрицательным")
        positive_safety = {
            "SAFETY_CHECK_INTERVAL_SECONDS": self.safety_check_interval_seconds,
            "SAFETY_STARTUP_GRACE_SECONDS": self.safety_startup_grace_seconds,
            "SAFETY_PAYOUT_STUCK_SECONDS": self.safety_payout_stuck_seconds,
            "SAFETY_WSS_STALE_SECONDS": self.safety_wss_stale_seconds,
            "SAFETY_HTTP_SCAN_STALE_SECONDS": self.safety_http_scan_stale_seconds,
            "SAFETY_INTEGRITY_INTERVAL_SECONDS": self.safety_integrity_interval_seconds,
            "SAFETY_BACKUP_INTERVAL_SECONDS": self.safety_backup_interval_seconds,
            "SAFETY_BACKUP_STALE_SECONDS": self.safety_backup_stale_seconds,
            "SAFETY_BACKUP_RETENTION_COUNT": self.safety_backup_retention_count,
        }
        invalid_safety = [name for name, value in positive_safety.items() if int(value) <= 0]
        if invalid_safety:
            raise ValueError("safety-настройки должны быть положительными: " + ", ".join(invalid_safety))

        seed_phrase = (
            self.payout_seed_phrase.get_secret_value().strip()
            if self.payout_seed_phrase is not None
            else ""
        )
        if seed_phrase:
            if len(seed_phrase.split()) not in {12, 15, 18, 21, 24}:
                raise ValueError(
                    "SEED_PHRASE должна содержать 12, 15, 18, 21 или 24 слова"
                )
            try:
                Account.enable_unaudited_hdwallet_features()
                seed_account = Account.from_mnemonic(
                    seed_phrase, account_path=self.seed_account_path
                )
            except Exception as exc:
                raise ValueError(
                    "не удалось получить EVM-кошелёк из SEED_PHRASE; "
                    "проверьте слова и SEED_ACCOUNT_PATH"
                ) from exc
            # В простом режиме отдельный TREASURY_ADDRESS не нужен: адрес приёма
            # автоматически становится первым EVM-адресом, полученным из seed-фразы.
            configured_treasury = self.treasury_address.strip()
            if not configured_treasury:
                self.treasury_address = seed_account.address
            elif configured_treasury.lower() != seed_account.address.lower():
                raise ValueError(
                    "TREASURY_ADDRESS не совпадает с кошельком из SEED_PHRASE. "
                    "Для простого режима оставьте TREASURY_ADDRESS пустым."
                )
            else:
                self.treasury_address = seed_account.address

        has_keystore_path = self.payout_keystore_path is not None
        has_keystore_password = bool(
            self.payout_keystore_password
            and self.payout_keystore_password.get_secret_value()
        )
        if has_keystore_path != has_keystore_password:
            raise ValueError(
                "PAYOUT_KEYSTORE_PATH и PAYOUT_KEYSTORE_PASSWORD нужно указывать вместе"
            )
        if self.environment == "production" and self.simulate_payouts:
            raise ValueError("в production запрещён SIMULATE_PAYOUTS=true")
        if self.chain_enabled:
            if self.environment == "production" and self.chain_id != 56:
                raise ValueError(
                    "в production blockchain-режим должен использовать BSC Mainnet (BSC_CHAIN_ID=56)"
                )
            if self.environment == "testnet" and self.chain_id != 97:
                raise ValueError(
                    "в testnet blockchain-режим должен использовать BSC Testnet (BSC_CHAIN_ID=97)"
                )
            if self.environment == "development" and self.chain_id not in {56, 97}:
                raise ValueError("поддерживаются только BSC Mainnet (56) и BSC Testnet (97)")
            required = {
                "BSC_RPC_URL": self.bsc_rpc_url,
                "BSC_WSS_URL": self.bsc_wss_url,
                "TOKEN_CONTRACT": self.token_contract,
                "TREASURY_ADDRESS": self.treasury_address,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"не заполнены обязательные blockchain-настройки: {', '.join(missing)}")
            invalid_addresses = [
                name
                for name, value in {
                    "TOKEN_CONTRACT": self.token_contract,
                    "TREASURY_ADDRESS": self.treasury_address,
                }.items()
                if not EVM_ADDRESS_RE.fullmatch(value)
            ]
            if invalid_addresses:
                raise ValueError(
                    "неверный EVM-адрес: " + ", ".join(invalid_addresses)
                )
            if self.environment == "production" and self.scan_start_block <= 0:
                raise ValueError(
                    "в production задайте SCAN_START_BLOCK рядом с блоком запуска"
                )
            if not self.bsc_rpc_url.startswith(("https://", "http://")):
                raise ValueError("BSC_RPC_URL должен быть HTTP(S) JSON-RPC endpoint")
            if self.bsc_rpc_fallback_url and not self.bsc_rpc_fallback_url.startswith(
                ("https://", "http://")
            ):
                raise ValueError(
                    "BSC_RPC_FALLBACK_URL должен быть HTTP(S) JSON-RPC endpoint"
                )
            if not self.bsc_wss_url.startswith(("wss://", "ws://")):
                raise ValueError("BSC_WSS_URL должен быть WS(S) JSON-RPC endpoint")
            if self.environment == "production":
                if not self.bsc_rpc_url.startswith("https://"):
                    raise ValueError("в production BSC_RPC_URL должен начинаться с https://")
                if self.bsc_rpc_fallback_url and not self.bsc_rpc_fallback_url.startswith(
                    "https://"
                ):
                    raise ValueError(
                        "в production BSC_RPC_FALLBACK_URL должен начинаться с https://"
                    )
                if not self.bsc_wss_url.startswith("wss://"):
                    raise ValueError("в production BSC_WSS_URL должен начинаться с wss://")
            if self.simulate_payouts:
                raise ValueError("при CHAIN_ENABLED=true нужно установить SIMULATE_PAYOUTS=false")
            has_private_key = bool(
                self.payout_private_key and self.payout_private_key.get_secret_value()
            )
            has_keystore = bool(self.payout_keystore_path and has_keystore_password)
            signing_methods = sum(
                bool(item) for item in (seed_phrase, has_private_key, has_keystore)
            )
            if signing_methods == 0:
                raise ValueError(
                    "Для blockchain-выплат настройте один способ подписи; "
                    "на VPS рекомендуется encrypted keystore или secret-файл"
                )
            if signing_methods > 1:
                raise ValueError(
                    "Выберите только один способ подписи: SEED_PHRASE, keystore или private key"
                )
        return self


def format_settings_error(exc: ValidationError) -> str:
    """Возвращает короткую ошибку конфигурации без вывода секретов и полных RPC URL."""
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error.get("loc", ())) or "settings"
        message = str(error.get("msg", "неверное значение"))
        problems.append(f"- {location}: {message}")
    details = "\n".join(problems) if problems else "- неверная конфигурация .env"
    return (
        f"Ошибка конфигурации в {ENV_FILE}:\n{details}\n"
        "Откройте .env рядом с main.py и заполните как минимум BOT_TOKEN. "
        "Для реального blockchain-режима также заполните BSC_RPC_URL, BSC_WSS_URL, BSC_CHAIN_ID, "
        "TOKEN_CONTRACT и один способ подписи. Секреты можно передать через *_FILE."
    )
