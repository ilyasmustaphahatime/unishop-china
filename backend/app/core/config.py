from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class DatabaseConfigurationError(RuntimeError):
    """Raised when local database settings are missing or unsafe."""


class UnsafeRuntimeConfigurationError(RuntimeError):
    """Raised when development-only capabilities are configured outside development."""

    def __init__(self, unsafe_variables: list[str]) -> None:
        names = ", ".join(sorted(unsafe_variables))
        super().__init__(f"Unsafe runtime configuration variables: {names}")
        self.unsafe_variables = tuple(sorted(unsafe_variables))


class AuthenticationConfigurationError(RuntimeError):
    """Raised when access-token configuration is missing or unsafe."""

    def __init__(self, unsafe_variables: list[str]) -> None:
        names = ", ".join(sorted(unsafe_variables))
        super().__init__(f"Unsafe authentication configuration variables: {names}")
        self.unsafe_variables = tuple(sorted(unsafe_variables))


class Settings(BaseSettings):
    app_name: str = "UniShop China"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "unishop_china"
    mysql_user: str = "unishop_app"
    mysql_password: SecretStr | None = None
    database_url: str | None = None

    frontend_url: str = "http://localhost:5173"
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=5, le=60)
    jwt_issuer: str = "unishop-china-api"
    jwt_audience: str = "unishop-china-web"
    jwt_clock_skew_seconds: int = Field(default=30, ge=0, le=120)
    verification_code_hash_secret: SecretStr | None = None

    sms_enabled: bool = False
    sms_provider: str = "tencent"
    tencent_secret_id: SecretStr | None = None
    tencent_secret_key: SecretStr | None = None
    tencent_sms_sdk_app_id: str | None = None
    tencent_sms_signature: str | None = None
    tencent_sms_template_id: str | None = None
    tencent_sms_region: str = "ap-guangzhou"
    tencent_sms_endpoint: str = "sms.tencentcloudapi.com"
    sms_request_timeout_seconds: int = Field(default=10, ge=1, le=30)
    enable_fake_sms_dev_inbox: bool = False
    fake_sms_delivery_delay_seconds: float = Field(default=3, ge=0, le=20)
    fake_sms_inbox_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    fake_sms_inbox_max_messages: int = Field(default=100, ge=1, le=1000)
    fake_sms_localhost_only: bool = True
    registration_rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    registration_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    registration_rate_limit_max_clients: int = Field(default=10000, ge=100, le=100000)
    login_ip_rate_limit_requests: int = Field(default=5, ge=1, le=100)
    login_ip_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    login_identifier_rate_limit_requests: int = Field(default=10, ge=1, le=100)
    login_identifier_rate_limit_window_seconds: int = Field(default=900, ge=60, le=86400)
    login_rate_limit_max_keys: int = Field(default=10000, ge=100, le=100000)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def validate_runtime_security(config: Settings) -> None:
    environment = config.app_env.strip().lower()
    provider = config.sms_provider.strip().lower()
    unsafe: list[str] = []

    if environment != "development" and provider == "fake":
        unsafe.extend(["APP_ENV", "SMS_PROVIDER"])
    if environment != "development" and config.enable_fake_sms_dev_inbox:
        unsafe.extend(["APP_ENV", "ENABLE_FAKE_SMS_DEV_INBOX"])
    if config.enable_fake_sms_dev_inbox and not config.fake_sms_localhost_only:
        unsafe.append("FAKE_SMS_LOCALHOST_ONLY")

    if unsafe:
        raise UnsafeRuntimeConfigurationError(list(set(unsafe)))

    validate_authentication_configuration(config)


def validate_authentication_configuration(config: Settings) -> None:
    unsafe: list[str] = []
    secret = (
        config.jwt_secret_key.get_secret_value().strip()
        if config.jwt_secret_key is not None
        else ""
    )
    placeholder_markers = ("replace_with", "change_me", "local_secret", "your_secret")

    if len(secret) < 32 or any(marker in secret.lower() for marker in placeholder_markers):
        unsafe.append("JWT_SECRET_KEY")
    if config.jwt_algorithm.strip().upper() != "HS256":
        unsafe.append("JWT_ALGORITHM")
    if not config.jwt_issuer.strip():
        unsafe.append("JWT_ISSUER")
    if not config.jwt_audience.strip():
        unsafe.append("JWT_AUDIENCE")

    if unsafe:
        raise AuthenticationConfigurationError(unsafe)


def _is_placeholder_password(password: str) -> bool:
    normalized = password.strip().lower()
    placeholder_markers = (
        "change_me",
        "replace_with",
        "local_secret",
        "your_password",
    )
    return not normalized or any(marker in normalized for marker in placeholder_markers)


def build_database_url(settings: Settings) -> URL:
    """Return one validated MySQL/PyMySQL URL without manual password encoding."""
    explicit_url = (settings.database_url or "").strip()
    if explicit_url:
        try:
            url = make_url(explicit_url)
        except ArgumentError as exc:
            raise DatabaseConfigurationError("DATABASE_URL is not a valid SQLAlchemy URL.") from exc

        if url.drivername != "mysql+pymysql":
            raise DatabaseConfigurationError("DATABASE_URL must use the mysql+pymysql driver.")
        if url.username != "unishop_app":
            raise DatabaseConfigurationError(
                "DATABASE_URL must use the dedicated unishop_app user."
            )
        if url.database != "unishop_china":
            raise DatabaseConfigurationError("DATABASE_URL must target the unishop_china database.")
        return url.update_query_dict({"charset": "utf8mb4"})

    if settings.mysql_user != "unishop_app":
        raise DatabaseConfigurationError("MYSQL_USER must be the dedicated unishop_app user.")
    if settings.mysql_database != "unishop_china":
        raise DatabaseConfigurationError("MYSQL_DATABASE must be unishop_china.")
    if settings.mysql_password is None:
        raise DatabaseConfigurationError("MYSQL_PASSWORD is missing from backend/.env.")

    password = settings.mysql_password.get_secret_value()
    if _is_placeholder_password(password):
        raise DatabaseConfigurationError(
            "MYSQL_PASSWORD is still a placeholder in backend/.env; set the local unishop_app password."
        )

    return URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
