"""Ordered trace of requests, accepted choices and execution events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceRecorder:
    requests: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def record_request(self, side: str, payload: dict[str, Any]) -> None:
        self.requests.append({"side": side, "request": payload})

    def record_choice(self, side: str, choice: dict[str, Any]) -> None:
        self.choices.append({"side": side, "choice": choice})

    def record_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def to_meta(self) -> dict[str, Any]:
        return {
            "trace": {
                "requests": self.requests,
                "choices": self.choices,
                "events": self.events,
            }
        }
