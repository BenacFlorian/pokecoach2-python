"""Engine and bridge error types."""

from __future__ import annotations


class EngineError(Exception):
    """Base class for simulation engine failures."""


class EngineProtocolError(EngineError):
    """Invalid or unexpected JSONL protocol message."""


class EngineBridgeError(EngineError):
    """Bridge subprocess or VGC runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class EngineUnavailableError(EngineBridgeError):
    """Engine not configured or failed to start."""
