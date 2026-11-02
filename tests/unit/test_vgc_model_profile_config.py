from __future__ import annotations

from pokecoach_python.core.config import Settings


def test_vgc_engine_configured_with_model_profile(monkeypatch, tmp_path):
    profile = tmp_path / "vgc_model.yaml"
    profile.write_text("model_id: x\ncheckpoint:\n  path: x.zip\n", encoding="utf-8")
    monkeypatch.setenv("VGC_MODEL_PROFILE", str(profile))
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    from pokecoach_python.core.config import reset_settings_cache

    reset_settings_cache()
    settings = Settings()
    assert settings.vgc_engine_configured() is True
