"""Application settings and database URL construction."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "container"] = Field(alias="APP_ENV", default="local")
    postgres_host: str = Field(alias="POSTGRES_HOST", default="127.0.0.1")
    postgres_port: int = Field(alias="POSTGRES_PORT", default=5442)
    postgres_db: str = Field(alias="POSTGRES_DB", default="pokecoach2")
    postgres_user: str = Field(alias="POSTGRES_USER", default="pokecoach_worker")
    postgres_password: SecretStr = Field(alias="POSTGRES_PASSWORD")
    db_connect_timeout_seconds: int = Field(alias="DB_CONNECT_TIMEOUT_SECONDS", default=5)
    enable_demo_seed: bool = Field(alias="ENABLE_DEMO_SEED", default=False)
    analysis_regulations: str = Field(
        alias="ANALYSIS_REGULATIONS",
        default="M-B",
    )
    analysis_deployed_phases: str = Field(
        alias="ANALYSIS_DEPLOYED_PHASES",
        default="A,B,C,D,synthesis",
    )
    analysis_checkpoint_id: str = Field(
        alias="ANALYSIS_CHECKPOINT_ID",
        default="stub-bc-v1",
    )
    analysis_preview_timeout_seconds: float = Field(
        alias="ANALYSIS_PREVIEW_TIMEOUT_SECONDS",
        default=30.0,
    )
    engine_mode: str = Field(alias="POKECOACH_ENGINE", default="stub")
    vgc_bench_root: str | None = Field(alias="VGC_BENCH_ROOT", default=None)

    def analysis_regulation_list(self) -> list[str]:
        return [part.strip() for part in self.analysis_regulations.split(",") if part.strip()]

    def analysis_regulation_default(self) -> str:
        values = self.analysis_regulation_list()
        if not values:
            raise ValueError("ANALYSIS_REGULATIONS must not be empty")
        return values[0]

    def analysis_deployed_phase_list(self) -> list[str]:
        return [
            part.strip()
            for part in self.analysis_deployed_phases.split(",")
            if part.strip()
        ]

    @field_validator("postgres_port")
    @classmethod
    def port_in_valid_range(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("POSTGRES_PORT must be between 1 and 65535")
        return value

    def safe_repr(self) -> str:
        return (
            f"Settings(app_env={self.app_env!r}, postgres_host={self.postgres_host!r}, "
            f"postgres_port={self.postgres_port}, postgres_db={self.postgres_db!r}, "
            f"postgres_user={self.postgres_user!r}, postgres_password='***', "
            f"db_connect_timeout_seconds={self.db_connect_timeout_seconds}, "
            f"enable_demo_seed={self.enable_demo_seed})"
        )


def build_database_url(settings: Settings) -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        query={"connect_timeout": str(settings.db_connect_timeout_seconds)},
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
