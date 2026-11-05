"""Application settings and database URL construction."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    _ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        extra="ignore",
    )

    app_env: Literal["local", "container"] = Field(alias="APP_ENV", default="local")
    postgres_host: str = Field(alias="POSTGRES_HOST", default="127.0.0.1")
    postgres_port: int = Field(alias="POSTGRES_PORT", default=5442)
    postgres_db: str = Field(alias="POSTGRES_DB", default="pokecoach2")
    postgres_user: str = Field(alias="POSTGRES_USER", default="pokecoach_worker")
    postgres_password: SecretStr = Field(alias="POSTGRES_PASSWORD")
    db_connect_timeout_seconds: int = Field(
        alias="DB_CONNECT_TIMEOUT_SECONDS", default=5
    )
    enable_demo_seed: bool = Field(alias="ENABLE_DEMO_SEED", default=False)
    analysis_regulations: str = Field(
        alias="ANALYSIS_REGULATIONS",
        default="M-B",
    )
    analysis_deployed_phases: str = Field(
        alias="ANALYSIS_DEPLOYED_PHASES",
        default="A,C,B,D,synthesis",
    )
    analysis_checkpoint_id: str = Field(
        alias="ANALYSIS_CHECKPOINT_ID",
        default="stub-bc-v1",
    )
    analysis_preview_timeout_seconds: float = Field(
        alias="ANALYSIS_PREVIEW_TIMEOUT_SECONDS",
        default=90.0,
    )
    engine_mode: str = Field(alias="POKECOACH_ENGINE", default="stub")
    vgc_bench_root: str | None = Field(alias="VGC_BENCH_ROOT", default=None)
    vgc_bridge_python: str | None = Field(alias="VGC_BRIDGE_PYTHON", default=None)
    vgc_bridge_manifest_path: str | None = Field(
        alias="VGC_BRIDGE_MANIFEST", default=None
    )
    vgc_checkpoint_path: str | None = Field(alias="VGC_CHECKPOINT_PATH", default=None)
    vgc_checkpoint_sha256: str | None = Field(
        alias="VGC_CHECKPOINT_SHA256", default=None
    )
    vgc_model_profile: str | None = Field(alias="VGC_MODEL_PROFILE", default=None)
    showdown_server_url: str = Field(
        alias="SHOWDOWN_SERVER_URL",
        default="ws://127.0.0.1:8090/showdown/websocket",
    )
    engine_startup_timeout_seconds: float = Field(
        alias="ENGINE_STARTUP_TIMEOUT_SECONDS",
        default=120.0,
    )
    engine_preflight_timeout_seconds: float = Field(
        alias="ENGINE_PREFLIGHT_TIMEOUT_SECONDS",
        default=60.0,
    )
    engine_first_turn_timeout_seconds: float = Field(
        alias="ENGINE_FIRST_TURN_TIMEOUT_SECONDS",
        default=120.0,
    )
    engine_full_battle_timeout_seconds: float = Field(
        alias="ENGINE_FULL_BATTLE_TIMEOUT_SECONDS",
        default=300.0,
    )
    engine_max_reject_previews: int = Field(
        alias="ENGINE_MAX_REJECT_PREVIEWS", default=500
    )
    regulation_showdown_map: str = Field(
        alias="REGULATION_SHOWDOWN_MAP",
        default='{"M-B":"gen9championsvgc2026regmb","M-A":"gen9championsvgc2026regma","M-C":"gen9championsvgc2026regmc"}',
    )
    llm_model: str = Field(
        alias="LLM_MODEL",
        default="deepseek-ai/DeepSeek-V4.1-Flash-1017",
    )
    llm_input_token_budget: int = Field(alias="LLM_INPUT_TOKEN_BUDGET", default=100_000)
    llm_output_token_budget: int = Field(alias="LLM_OUTPUT_TOKEN_BUDGET", default=1200)
    llm_timeout_seconds: float = Field(alias="LLM_TIMEOUT_SECONDS", default=45.0)
    deepinfra_api_key: SecretStr | None = Field(alias="DEEPINFRA_API_KEY", default=None)

    def analysis_regulation_list(self) -> list[str]:
        return [
            part.strip()
            for part in self.analysis_regulations.split(",")
            if part.strip()
        ]

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

    def regulation_showdown_map_json(self) -> str:
        return self.regulation_showdown_map

    def synthesis_enabled(self) -> bool:
        if "synthesis" not in self.analysis_deployed_phase_list():
            return False
        if self.deepinfra_api_key is None:
            return False
        return bool(self.deepinfra_api_key.get_secret_value().strip())

    def synthesis_model_name(self) -> str:
        model = self.llm_model.strip()
        if not model:
            raise ValueError("LLM_MODEL must not be empty")
        return model

    def synthesis_output_token_limit(self) -> int:
        if self.llm_output_token_budget <= 0:
            raise ValueError("LLM_OUTPUT_TOKEN_BUDGET must be positive")
        return self.llm_output_token_budget

    def synthesis_source_token_budget(self, prompt_overhead_tokens: int = 512) -> int:
        if self.llm_input_token_budget <= 0:
            raise ValueError("LLM_INPUT_TOKEN_BUDGET must be positive")
        available = (
            self.llm_input_token_budget
            - self.synthesis_output_token_limit()
            - prompt_overhead_tokens
        )
        if available <= 0:
            raise ValueError("LLM_INPUT_TOKEN_BUDGET too small for synthesis")
        return available

    def synthesis_base_url(self) -> str:
        return "https://api.deepinfra.com/v1/openai"

    def regulation_to_showdown_format(self, regulation: str) -> str:
        try:
            mapping = json.loads(self.regulation_showdown_map)
        except json.JSONDecodeError as exc:
            raise ValueError("REGULATION_SHOWDOWN_MAP must be valid JSON") from exc
        if not isinstance(mapping, dict):
            raise ValueError("REGULATION_SHOWDOWN_MAP must be a JSON object")
        fmt = mapping.get(regulation)
        if not isinstance(fmt, str) or not fmt:
            raise ValueError(f"no Showdown format mapped for regulation {regulation!r}")
        return fmt

    def default_bridge_manifest_path(self) -> str:
        if self.vgc_bridge_manifest_path:
            return self.vgc_bridge_manifest_path
        root = Path(__file__).resolve().parents[3]
        return str(root / "engine-runtime" / "manifest.json")

    def resolved_vgc_bridge_python(self) -> str:
        if self.vgc_bridge_python:
            return self.vgc_bridge_python
        root = Path(__file__).resolve().parents[3]
        candidate = root / "engine-runtime" / ".venv" / "bin" / "python"
        if candidate.is_file():
            return str(candidate)
        import sys

        return sys.executable

    def vgc_engine_configured(self) -> bool:
        if self.vgc_model_profile:
            return True
        return bool(self.vgc_checkpoint_path)

    @property
    def vgc_bridge_argv(self) -> list[str] | None:
        return None

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
