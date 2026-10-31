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
        Settings(POSTGRES_PASSWORD="secret", POSTGRES_PORT=70000)


def test_missing_password_rejected():
    with pytest.raises(ValidationError):
        Settings()


def test_password_special_chars_preserved_in_url():
    password = "a@b:c/d%"
    settings = Settings(POSTGRES_PASSWORD=password)
    url = build_database_url(settings)
    assert url.password == password


def test_safe_repr_masks_password():
    settings = Settings(POSTGRES_PASSWORD="secret")
    text = settings.safe_repr()
    assert "secret" not in text
    assert "***" in text
