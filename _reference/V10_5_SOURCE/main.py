import uvicorn
from pydantic import ValidationError

from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings, format_settings_error
from delta_backend.logging_config import configure_logging


if __name__ == "__main__":
    configure_logging()
    try:
        Settings()
        settings = MiniAppSettings()
        settings.validate_business_rules()
    except ValidationError as exc:
        raise SystemExit(format_settings_error(exc)) from None
    except ValueError as exc:
        raise SystemExit(f"Ошибка конфигурации: {exc}") from None
    uvicorn.run(
        "delta_backend.api:app",
        host=settings.api_host,
        port=settings.api_port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        workers=1,
    )
