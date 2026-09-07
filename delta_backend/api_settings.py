from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# NOVERA Telegram session compatibility


class MiniAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    miniapp_url: str = "http://localhost:3000"
    miniapp_origin: str = "http://localhost:3000"
    bot_username: str = "NoveraBot"
    run_bot_launcher: bool = True
    run_broadcast_worker: bool = True
    demo_mode: bool = True
    telegram_init_data_ttl_seconds: int = 86400
    telegram_session_ttl_seconds: int = 604800
    trusted_hosts: str = "localhost,127.0.0.1"
    force_https: bool = False
    max_request_bytes: int = 65_536
    mutation_rate_limit: int = 12
    mutation_rate_window_seconds: int = 60

    daily_profit_bps: int = 1000
    payout_days: int = 20
    deposit_min_usdt: int = 10
    deposit_max_usdt: int = 100_000
    invoice_ttl_minutes: int = 30

    referral_level_bps: tuple[int, ...] = (800, 400, 250, 150, 100)
    referral_personal_thresholds_usdt: tuple[int, ...] = (50, 100, 300, 500, 1000)
    referral_line_thresholds_usdt: tuple[int, ...] = (100, 300, 500, 1500, 5000)

    api_host: str = "0.0.0.0"
    api_port: int = 8080
    forwarded_allow_ips: str = "127.0.0.1"

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    def validate_business_rules(self) -> None:
        lengths = {
            len(self.referral_level_bps),
            len(self.referral_personal_thresholds_usdt),
            len(self.referral_line_thresholds_usdt),
        }
        if lengths != {5}:
            raise ValueError("Referral settings must contain exactly five levels")
        if self.daily_profit_bps <= 0 or self.payout_days <= 0:
            raise ValueError("Daily payout settings must be positive")
        if self.deposit_min_usdt <= 0 or self.deposit_max_usdt < self.deposit_min_usdt:
            raise ValueError("Invalid deposit limits")
        if not 60 <= self.telegram_init_data_ttl_seconds <= 86_400:
            raise ValueError("Telegram initData TTL must be between 60 and 86400 seconds")
        if not 3_600 <= self.telegram_session_ttl_seconds <= 7_776_000:
            raise ValueError("NOVERA session TTL must be between 3600 and 7776000 seconds")
        if self.max_request_bytes < 4096:
            raise ValueError("MAX_REQUEST_BYTES is too small")
        if self.mutation_rate_limit <= 0 or self.mutation_rate_window_seconds <= 0:
            raise ValueError("Mutation rate limit settings must be positive")
        if not self.trusted_host_list:
            raise ValueError("TRUSTED_HOSTS must contain at least one host")
        origin = urlsplit(self.miniapp_origin)
        if not origin.scheme or not origin.netloc or origin.path not in {"", "/"}:
            raise ValueError("MINIAPP_ORIGIN must be an origin without a path")
        miniapp = urlsplit(self.miniapp_url)
        if not miniapp.scheme or not miniapp.netloc:
            raise ValueError("MINIAPP_URL must be an absolute URL")
