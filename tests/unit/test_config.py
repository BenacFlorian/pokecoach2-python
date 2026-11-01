import pytest
from pydantic import ValidationError

from pokecoach_python.core.config import Settings, build_database_url, reset_settings_cache


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_port_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, POSTGRES_PASSWORD="secret", POSTGRES_PORT=70000)


def test_missing_password_rejected(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=())


def test_password_special_chars_preserved_in_url():
    password = "a@b:c/d%"
    settings = Settings(_env_file=None, POSTGRES_PASSWORD=password)
    url = build_database_url(settings)
    assert url.password == password


def test_safe_repr_masks_password():
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")
    text = settings.safe_repr()
    assert "secret" not in text
    assert "***" in text


def test_synthesis_disabled_without_deepinfra_key():
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")
    assert settings.synthesis_enabled() is False


def test_synthesis_budget_helpers():
    settings = Settings(
        _env_file=None,
        POSTGRES_PASSWORD="secret",
        DEEPINFRA_API_KEY="fake-key",
        LLM_INPUT_TOKEN_BUDGET=10000,
        LLM_OUTPUT_TOKEN_BUDGET=1500,
    )
    assert settings.synthesis_enabled() is True
    assert settings.synthesis_model_name() == "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    assert settings.synthesis_output_token_limit() == 1500
    assert settings.synthesis_source_token_budget(prompt_overhead_tokens=500) == 8000
