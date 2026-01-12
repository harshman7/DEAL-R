"""Server configuration using Pydantic settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite:///./poker.db"

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours for game sessions

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    # Snapshots
    snapshot_interval: int = 100  # Create snapshot every N events


settings = Settings()
