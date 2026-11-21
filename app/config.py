from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "F1 Telemetry Monitoring Platform"

    # Either set DATABASE_URL directly, or the individual DB_* parts.
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "telematics"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # Required in the X-API-Key header for write endpoints (ingest, alert actions).
    api_key: str = "change-me"

    # Alert thresholds
    alert_max_rpm: int = 12500
    alert_max_speed_kph: int = 340
    alert_slow_lap_ratio: float = 1.07  # F1 "107% rule" vs. session fastest lap

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
