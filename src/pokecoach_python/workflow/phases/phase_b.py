"""Phase B — conditioned turn-1 openings for each opponent lead from phase A."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from typing import Any

from pokecoach_python.core.analysis_errors import RunExecutionStopped
from pokecoach_python.engine.contracts import SimulationRequest, TurnOneRecord
from pokecoach_python.engine.errors import EngineBridgeError
from pokecoach_python.engine.seeds import phase_attempt_seed
from pokecoach_python.schemas.analysis_result import (
    LeadPickSection,
    OpponentLeadsSection,
    SimulationResultV2,
    validate_result,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.openings import aggregate_openings
from pokecoach_python.workflow.battle_records import canonical_four, validate_turn_one_selection
from pokecoach_python.workflow.budgets import max_attempts, phase_b_valid_budget
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput

_SAMPLING_POLICY = "conditional-back-v1"
_logger = logging.getLogger(__name__)
_VERBOSE_REJECTS = os.environ.get("POKECOACH_DEBUG_PHASE_B", "").strip() in {
    "1",
    "true",
    "yes",
}


def _reject_bucket(*, bucket: str, detail: str) -> tuple[str, str]:
    key = bucket.strip() or "unknown"
    return key, detail.strip()


def _reject_from_exception(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, EngineBridgeError):
        msg = str(exc)
        code = getattr(exc, "code", "") or "ENGINE_BRIDGE"
        if "TURN1_EXTRACT" in msg:
            head = msg.split(":", 1)[0].strip()
            return _reject_bucket(bucket=head, detail=msg)
        if ":" in msg:
            head = msg.split(":", 1)[0].strip()
            return _reject_bucket(bucket=head, detail=msg)
        return _reject_bucket(bucket=code, detail=msg)
    if isinstance(exc, ValueError):
        return _reject_bucket(bucket="validation", detail=str(exc))
    return _reject_bucket(bucket=type(exc).__name__, detail=str(exc))


def _log_phase_b_reject(
    *,
    lead_id: str,
    attempt: int,
    bucket: str,
    detail: str,
    reject_counts: Counter[str],
    reject_samples: list[str],
) -> None:
    reject_counts[bucket] += 1
    line = f"attempt={attempt} [{bucket}] {detail}"
    if line not in reject_samples and len(reject_samples) < 12:
        reject_samples.append(line)
    if _VERBOSE_REJECTS or reject_counts[bucket] <= 3 or attempt <= 5:
        _logger.warning("phase B reject lead=%s %s", lead_id, line)
    else:
        _logger.debug("phase B reject lead=%s %s", lead_id, line)


def _attempt_seed(run_seed: int, lead_index: int, attempt: int) -> int:
    return phase_attempt_seed(run_seed, "B", lead_index, attempt)


def _load_phase_ac(partial: dict[str, Any]) -> tuple[OpponentLeadsSection, LeadPickSection]:
    if partial.get("completedPhases") != ["A", "C"]:
        raise RuntimeError("phase B requires completed phases A and C")
    payload = {
        "schemaVersion": 2,
        "source": "simulation",
        "openings": None,
        "refinement": None,
        "gameplan": None,
        "winCondition": None,
        **partial,
    }
    try:
        validated = validate_result(payload)
    except ValueError as exc:
        raise RuntimeError("phase B requires valid A+C checkpoint") from exc
    if (
        validated.completedPhases != ["A", "C"]
        or validated.opponentLeads is None
        or validated.leadPick is None
    ):
        raise RuntimeError("phase B requires opponentLeads and leadPick from A+C")
    return validated.opponentLeads, validated.leadPick


def run_phase_b(context: PhaseContext) -> PhaseOutput:
    section_a, lead_pick = _load_phase_ac(context.partial_result)
    selection = lead_pick.selection
    our_four = canonical_four(selection.ourFourSlots)
    our_lead = canonical_lead(selection.ourLeadSlots)
    budget = phase_b_valid_budget(context.profile)
    per_lead_cap = max_attempts(budget)
    total_target = len(section_a.leads) * budget
    done_global = 0
    attempts_total = 0
    rejects_total = 0
    errors_total = 0
    records_by_id: dict[str, list[TurnOneRecord]] = {}

    context.report_progress("B", 0, total_target)

    for lead_index, entry in enumerate(section_a.leads):
        lead_slots = canonical_lead(entry.slots)
        valid: list[TurnOneRecord] = []
        attempts = 0
        rejects = 0
        errors = 0
        reject_counts: Counter[str] = Counter()
        reject_samples: list[str] = []
        error_samples: list[str] = []

        while len(valid) < budget and attempts < per_lead_cap:
            attempts += 1
            attempts_total += 1
            context.ensure_active()
            req = SimulationRequest(
                our_snapshot=context.our_snapshot,
                opponent_snapshot=context.opponent_snapshot,
                regulation=context.regulation,
                checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
                seed=_attempt_seed(context.seed, lead_index, attempts),
                timeout_seconds=context.first_turn_timeout_seconds,
                opponent_lead=lead_slots,
                our_selection=our_four,
                our_lead_slots=our_lead,
            )
            try:
                record = context.engine.first_turn(req)
                observed_lead = canonical_lead(record.opponent_lead_slots)
                if observed_lead != lead_slots:
                    rejects += 1
                    rejects_total += 1
                    bucket, detail = _reject_bucket(
                        bucket="opponent_lead_mismatch",
                        detail=(
                            f"expected {lead_slots} observed {observed_lead} "
                            f"preview={record.payload.get('previewAccepted')!r}"
                        ),
                    )
                    _log_phase_b_reject(
                        lead_id=entry.id,
                        attempt=attempts,
                        bucket=bucket,
                        detail=detail,
                        reject_counts=reject_counts,
                        reject_samples=reject_samples,
                    )
                    continue
                validate_turn_one_selection(
                    record.payload,
                    our_four=our_four,
                    our_lead=our_lead,
                    opponent_lead=lead_slots,
                )
                valid.append(record)
                done_global += 1
                context.report_progress("B", done_global, total_target)
            except RunExecutionStopped:
                raise
            except ValueError as exc:
                rejects += 1
                rejects_total += 1
                bucket, detail = _reject_from_exception(exc)
                _log_phase_b_reject(
                    lead_id=entry.id,
                    attempt=attempts,
                    bucket=bucket,
                    detail=detail,
                    reject_counts=reject_counts,
                    reject_samples=reject_samples,
                )
            except EngineBridgeError as exc:
                message = str(exc)
                if "TURN1_EXTRACT" in message or "move evidence missing" in message.lower():
                    rejects += 1
                    rejects_total += 1
                    bucket, detail = _reject_from_exception(exc)
                    _log_phase_b_reject(
                        lead_id=entry.id,
                        attempt=attempts,
                        bucket=bucket,
                        detail=detail,
                        reject_counts=reject_counts,
                        reject_samples=reject_samples,
                    )
                else:
                    errors += 1
                    errors_total += 1
                    bucket, detail = _reject_from_exception(exc)
                    line = f"attempt={attempts} [{bucket}] {detail}"
                    if len(error_samples) < 8 and line not in error_samples:
                        error_samples.append(line)
                    _logger.warning(
                        "phase B bridge error lead=%s attempt=%s [%s] %s",
                        entry.id,
                        attempts,
                        bucket,
                        detail,
                    )
            except Exception as exc:
                errors += 1
                errors_total += 1
                bucket, detail = _reject_from_exception(exc)
                line = f"attempt={attempts} [{bucket}] {detail}"
                if len(error_samples) < 8 and line not in error_samples:
                    error_samples.append(line)
                _logger.warning(
                    "phase B error lead=%s attempt=%s [%s] %s",
                    entry.id,
                    attempts,
                    bucket,
                    detail,
                )

        if len(valid) < budget:
            breakdown = ", ".join(f"{k}={v}" for k, v in reject_counts.most_common(12))
            _logger.error(
                "phase B budget not met lead=%s valid=%s/%s attempts=%s rejects=%s errors=%s "
                "our_four=%s our_lead=%s opponent_lead=%s breakdown=[%s]",
                entry.id,
                len(valid),
                budget,
                attempts,
                rejects,
                errors,
                our_four,
                our_lead,
                lead_slots,
                breakdown or "none",
            )
            if reject_samples:
                _logger.error(
                    "phase B reject samples lead=%s (max 12, set POKECOACH_DEBUG_PHASE_B=1 for all): %s",
                    entry.id,
                    reject_samples,
                )
            if error_samples:
                _logger.error("phase B error samples lead=%s: %s", entry.id, error_samples)
            raise RuntimeError(
                f"phase B budget not met for {entry.id}: {len(valid)}/{budget} "
                f"(attempts={attempts}, rejects={rejects}, errors={errors}); "
                f"reject breakdown: {breakdown or 'none'}"
            )

        records_by_id[entry.id] = valid

    openings = aggregate_openings(
        records_by_id,
        section_a.leads,
        selection,
        sampling_policy=_SAMPLING_POLICY,
    )
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "C", "B"],
        opponentLeads=section_a,
        leadPick=lead_pick,
        openings=openings,
        refinement=None,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            {lead_id: len(recs) for lead_id, recs in records_by_id.items()},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    compact_samples: list[dict[str, Any]] = []
    for lead_id, recs in records_by_id.items():
        for index, record in enumerate(recs):
            payload = record.payload
            compact_samples.append(
                {
                    "leadId": lead_id,
                    "sampleIndex": index,
                    "ourFourSlots": list(our_four),
                    "ourLeadSlots": list(our_lead),
                    "opponentLeadSlots": list(record.opponent_lead_slots),
                    "previewAccepted": payload.get("previewAccepted"),
                    "turnEvents": payload.get("turnEvents") or [],
                }
            )
    return PhaseOutput(
        phase="B",
        result=envelope,
        execution_slice={
            "phase": "B",
            "attempts": attempts_total,
            "rejects": rejects_total,
            "errors": errors_total,
            "leadsProcessed": len(section_a.leads),
            "budgetPerLead": budget,
            "samplingPolicy": _SAMPLING_POLICY,
            "auditFingerprint": audit_fingerprint,
            "samples": compact_samples,
        },
        metadata_patch={"phases": {"B": {"samples": compact_samples}}},
    )
