from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/lunar_navigator"
    cors_origins: list[str] = ["http://localhost:5173"]
    horizons_api_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"
    horizons_timeout_seconds: float = Field(default=15.0, gt=0, le=30)
    observation_timeout_seconds: int = Field(default=120, ge=1, le=300)
    observation_cache_seconds: int = Field(default=3600, ge=1)
    result_retention_days: int = Field(default=7, ge=7)
    csa_cache_seconds: int = Field(default=300, ge=1)
    csa_stale_seconds: int = Field(default=86400, ge=1)

    @model_validator(mode="after")
    def cache_policy(self):
        if self.csa_stale_seconds < self.csa_cache_seconds:
            raise ValueError("CSA stale retention must not be shorter than its cache TTL")
        return self

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or "*" in origin
                or parts.path
                or parts.query
                or parts.fragment
                or parts.username
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP origins without paths")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
