import pytest
from pydantic import ValidationError

from delta_backend.api import validate_deployment_settings
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings


def chain_settings(**overrides):
    defaults = {
        "_env_file": None,
        "bot_token": "123456:TEST",
        "environment": "testnet",
        "chain_enabled": False,
        "simulate_payouts": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_production_rejects_demo_mode() -> None:
    chain = chain_settings(environment="production", simulate_payouts=False)
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=True,
        miniapp_url="https://mini.example.com",
        miniapp_origin="https://mini.example.com",
    )
    with pytest.raises(ValueError, match="DEMO_MODE"):
        validate_deployment_settings(chain, business)


def test_testnet_safe_defaults_are_valid() -> None:
    validate_deployment_settings(
        chain_settings(),
        MiniAppSettings(_env_file=None),
    )


def test_web_only_production_settings_are_valid() -> None:
    chain = chain_settings(
        environment="production",
        chain_enabled=False,
        simulate_payouts=False,
        deposits_enabled=False,
        investments_enabled=False,
        payouts_enabled=False,
    )
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        miniapp_url="https://mini.example.com",
        miniapp_origin="https://mini.example.com",
        trusted_hosts="api.example.com",
        force_https=True,
    )
    validate_deployment_settings(chain, business)


def live_chain_settings(**overrides):
    defaults = {
        "_env_file": None,
        "bot_token": "123456:TEST",
        "environment": "production",
        "chain_enabled": True,
        "simulate_payouts": False,
        "chain_id": 56,
        "bsc_rpc_url": "https://rpc.example.test",
        "bsc_wss_url": "wss://rpc.example.test/ws",
        "token_contract": "0x" + "11" * 20,
        "treasury_address": "0x" + "22" * 20,
        "payout_private_key": "0x" + "33" * 32,
        "scan_start_block": 123,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_vps_secret_files_are_supported(tmp_path) -> None:
    token_file = tmp_path / "bot-token"
    rpc_file = tmp_path / "rpc-url"
    wss_file = tmp_path / "wss-url"
    token_file.write_text("123456:FROM_FILE\n", encoding="utf-8")
    rpc_file.write_text("https://rpc.example.test\n", encoding="utf-8")
    wss_file.write_text("wss://rpc.example.test/ws\n", encoding="utf-8")

    settings = live_chain_settings(
        bot_token="",
        bot_token_file=token_file,
        bsc_rpc_url="",
        bsc_rpc_url_file=rpc_file,
        bsc_wss_url="",
        bsc_wss_url_file=wss_file,
    )

    assert settings.bot_token.get_secret_value() == "123456:FROM_FILE"
    assert settings.bsc_rpc_url == "https://rpc.example.test"
    assert settings.bsc_wss_url == "wss://rpc.example.test/ws"


def test_direct_secret_and_file_cannot_be_combined(tmp_path) -> None:
    token_file = tmp_path / "bot-token"
    token_file.write_text("123456:FROM_FILE", encoding="utf-8")

    with pytest.raises(ValidationError, match="только один источник"):
        chain_settings(bot_token_file=token_file)


def test_production_mainnet_is_allowed() -> None:
    settings = live_chain_settings(chain_id=56)
    assert settings.chain_id == 56


def test_production_rejects_testnet_chain_id() -> None:
    with pytest.raises(ValidationError, match="BSC Mainnet"):
        live_chain_settings(chain_id=97)


def test_production_chain_requires_recent_scan_start() -> None:
    with pytest.raises(ValidationError, match="SCAN_START_BLOCK"):
        live_chain_settings(scan_start_block=0)


def test_chain_rejects_invalid_addresses() -> None:
    with pytest.raises(ValidationError, match="неверный EVM-адрес"):
        live_chain_settings(token_contract="not-an-address")


def test_empty_file_environment_values_are_ignored(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "BOT_TOKEN=123456:TEST",
                "BOT_TOKEN_FILE=",
                "BSC_RPC_URL_FILE=",
                "BSC_RPC_FALLBACK_URL_FILE=",
                "BSC_WSS_URL_FILE=",
                "SEED_PHRASE_FILE=",
                "PAYOUT_SEED_PHRASE_FILE=",
                "PAYOUT_PRIVATE_KEY_FILE=",
                "PAYOUT_KEYSTORE_PATH=",
                "PAYOUT_KEYSTORE_PASSWORD_FILE=",
                "CHAIN_ENABLED=false",
                "SIMULATE_PAYOUTS=false",
                "ENVIRONMENT=production",
            ]
        ) + "\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.bot_token_file is None
    assert settings.bsc_rpc_url_file is None
    assert settings.bsc_rpc_fallback_url_file is None
    assert settings.bsc_wss_url_file is None
    assert settings.payout_seed_phrase_file is None
    assert settings.payout_private_key_file is None
    assert settings.payout_keystore_path is None
    assert settings.payout_keystore_password_file is None
