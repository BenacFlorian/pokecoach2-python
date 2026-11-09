"""DeepInfra-backed LLM client for structured strategy synthesis."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from hashlib import sha256
from typing import Any

from langchain_core.messages import BaseMessage

from pokecoach_python.core.analysis_errors import RunExecutionStopped
from pokecoach_python.core.config import Settings
from pokecoach_python.graphs.matchup_gameplan.models import PreparedSources, StrategyOutput


class StrategyClient:
    def __init__(
        self,
        settings: Settings,
        *,
        chat_factory: Any | None = None,
        ensure_active: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._chat_factory = chat_factory
        self._ensure_active = ensure_active or (lambda: None)
        self.last_invocation: dict[str, Any] | None = None

    def generate(
        self,
        sources: PreparedSources,
        messages: Sequence[BaseMessage],
    ) -> StrategyOutput:
        if not self._settings.synthesis_enabled():
            raise RuntimeError("synthesis is not configured")
        api_key = self._settings.deepinfra_api_key
        if api_key is None:
            raise RuntimeError("DEEPINFRA_API_KEY is required")
        prompt_text = "\n".join(str(message.content) for message in messages)
        prompt_hash = sha256(prompt_text.encode()).hexdigest()
        llm = self._build_llm(api_key.get_secret_value())
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            self._ensure_active()
            try:
                response = llm.invoke(list(messages))
                self._ensure_active()
                strategy = (
                    response
                    if isinstance(response, StrategyOutput)
                    else StrategyOutput.model_validate(response)
                )
                self.last_invocation = {
                    "model": self._settings.synthesis_model_name(),
                    "baseUrl": self._settings.synthesis_base_url(),
                    "promptHash": prompt_hash,
                    "sourcesHash": sources.sourceHash,
                    "attempts": attempts,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                    "tokens": _usage_metadata(response),
                }
                return strategy
            except RunExecutionStopped:
                raise
            except Exception as exc:
                if attempts >= 2 or not _is_transient_error(exc):
                    raise
                self._ensure_active()

    def _build_llm(self, api_key: str) -> Any:
        chat_factory = self._chat_factory
        if chat_factory is None:
            from langchain_openai import ChatOpenAI

            chat_factory = ChatOpenAI
        return chat_factory(
            model=self._settings.synthesis_model_name(),
            base_url=self._settings.synthesis_base_url(),
            api_key=api_key,
            timeout=float(self._settings.llm_timeout_seconds),
            max_retries=0,
            use_responses_api=False,
        ).with_structured_output(
            StrategyOutput,
            method="json_schema",
            strict=True,
        )


def _is_transient_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return int(status_code) >= 500
    return isinstance(exc, TimeoutError)


def _usage_metadata(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        return dict(usage)
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        token_usage = metadata.get("token_usage")
        if isinstance(token_usage, dict):
            return dict(token_usage)
    return None
