"""Phase A — opponent lead distribution."""

from __future__ import annotations

import hashlib
import json

from pokecoach_python.engine.contracts import PreviewRecord, SimulationRequest
from pokecoach_python.schemas.analysis_result import SimulationResultV2
from pokecoach_python.workflow.aggregation.leads import aggregate_leads
from pokecoach_python.workflow.budgets import max_attempts, phase_a_valid_budget
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput


def _attempt_seed(run_seed: int, attempt: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def run_phase_a(context: PhaseContext) -> PhaseOutput:
    budget = phase_a_valid_budget(context.profile)
    attempt_cap = max_attempts(budget)
    valid: list[PreviewRecord] = []
    attempts = 0
    rejects = 0
    errors = 0

    context.report_progress("A", 0, budget)

    while len(valid) < budget and attempts < attempt_cap:
        attempts += 1
        req = SimulationRequest(
            our_snapshot=context.our_snapshot,
            opponent_snapshot=context.opponent_snapshot,
            regulation=context.regulation,
            checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
            seed=_attempt_seed(context.seed, attempts),
            timeout_seconds=context.preview_timeout_seconds,
        )
        try:
            record = context.engine.preview(req)
            valid.append(record)
            context.report_progress("A", len(valid), budget)
        except ValueError:
            rejects += 1
        except Exception as exc:
            errors += 1
            if errors <= 3:
                import logging

                logging.getLogger(__name__).warning(
                    "phase A preview attempt %s failed: %s: %s",
                    attempts,
                    type(exc).__name__,
                    exc,
                )

    if len(valid) < budget:
        raise RuntimeError(
            f"phase A budget not met: {len(valid)}/{budget} valid "
            f"after {attempts} attempts (rejects={rejects}, errors={errors})"
        )

    section = aggregate_leads(valid)
    if section.sampleSize != budget:
        raise RuntimeError("phase A sample size mismatch")

    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A"],
        opponentLeads=section,
        leadPick=None,
        openings=None,
        refinement=None,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            [{"s": list(r.opponent_lead_slots)} for r in valid[:5]],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    return PhaseOutput(
        phase="A",
        result=envelope,
        execution_slice={
            "phase": "A",
            "attempts": attempts,
            "rejects": rejects,
            "errors": errors,
            "auditFingerprint": audit_fingerprint,
        },
        audit_traces=tuple(valid[:3]),
    )
