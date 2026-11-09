from pokecoach_python.core.config import Settings
from pokecoach_python.core.regulations import (
    canonical_regulation_allowed,
    canonical_regulation_label,
)


def test_canonical_regulation_labels() -> None:
    assert canonical_regulation_label("mc") == "M-C"
    assert canonical_regulation_label("M-B") == "M-B"
    assert canonical_regulation_label("MA") == "M-A"


def test_settings_analysis_regulation_list_includes_mc_by_default() -> None:
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")
    assert settings.analysis_regulation_list() == ["M-B", "M-A", "M-C"]


def test_canonical_regulation_allowed() -> None:
    assert canonical_regulation_allowed("M-C", ["M-B", "M-A", "M-C"])
    assert not canonical_regulation_allowed("M-C", ["M-B"])
