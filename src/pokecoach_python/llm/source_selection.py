"""Validate Phase E sources against Phase C selection."""

from __future__ import annotations

from pokecoach_python.graphs.matchup_gameplan.models import PreparedSources
from pokecoach_python.schemas.analysis_result import LeadSelection
from pokecoach_python.workflow.battle_records import canonical_four, canonical_lead


def validate_source_selection(
    sources: PreparedSources,
    selection: LeadSelection,
) -> None:
    expected_four = canonical_four(tuple(selection.ourFourSlots))
    expected_lead = canonical_lead(tuple(selection.ourLeadSlots))
    if len(sources.ourTeam) != 4:
        raise ValueError("synthesis sources must expose exactly our selected four")
    slots = {row.slot for row in sources.ourTeam}
    if slots != set(expected_four):
        raise ValueError("synthesis ourTeam slots must match selection C")
    for battle in sources.selectedBattles:
        if battle.ourFourSlots != expected_four:
            raise ValueError("selected D battle ourFourSlots mismatch with selection C")
        if battle.ourLeadSlots != expected_lead:
            raise ValueError("selected D battle ourLeadSlots mismatch with selection C")
