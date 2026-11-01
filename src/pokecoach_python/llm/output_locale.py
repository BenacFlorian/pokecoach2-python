"""Output language for LLM synthesis (aligned with Angular AppLocale)."""

from __future__ import annotations

from typing import Any, Literal

OutputLocale = Literal["fr", "en"]


def parse_output_locale(value: Any) -> OutputLocale:
    if value == "en":
        return "en"
    return "fr"


def locale_instruction(locale: OutputLocale) -> str:
    if locale == "en":
        return (
            "Write every user-facing string field in English "
            "(advice, explanations, descriptions, rationale, opening/midgame/endgame text)."
        )
    return (
        "Write every user-facing string field in French "
        "(conseils, explications, descriptions, rationale, textes opening/midgame/endgame)."
    )
