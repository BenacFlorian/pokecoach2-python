"""Cooperative stop and missing-target errors for analysis runs."""

from __future__ import annotations

import uuid
from typing import Literal

StopReason = Literal["missing_run", "lease_lost", "cancelled", "supervisor_stop"]
ResourceKind = Literal["matchup", "run"]


class RunExecutionStopped(Exception):
    """Expected stop: run gone, lease lost, cancel, or supervisor signal."""

    def __init__(
        self,
        reason: StopReason,
        *,
        run_id: uuid.UUID | None = None,
    ) -> None:
        self.reason = reason
        self.run_id = run_id
        super().__init__(reason)


class AnalysisTargetNotFound(Exception):
    """HTTP layer maps this to 404 when a matchup or run no longer exists."""

    def __init__(self, resource: ResourceKind, resource_id: uuid.UUID) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}")
