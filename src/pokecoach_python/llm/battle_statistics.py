"""Global statistics computed from all Phase D battles."""

from __future__ import annotations

from collections import defaultdict

from pokecoach_python.graphs.matchup_gameplan.models import (
    DStatistics,
    LeadFrequency,
    LeadResult,
    NormalizedDBattle,
    OurDamageStat,
    OutcomeCounts,
    PokemonRef,
    StatisticsQuality,
    ThreatStat,
)


def compute_d_statistics(records: list[NormalizedDBattle]) -> DStatistics:
    sample_size = len(records)
    if sample_size == 0:
        raise ValueError("cannot compute stats without D battles")
    wins = sum(1 for record in records if record.outcome == "win")
    losses = sum(1 for record in records if record.outcome == "loss")
    draws = sum(1 for record in records if record.outcome == "draw")
    lead_groups: dict[tuple[int, int], list[NormalizedDBattle]] = defaultdict(list)
    for record in records:
        lead_groups[record.opponentLeadSlots].append(record)
    leads = [
        LeadFrequency(
            leadId=_lead_id(slots),
            opponentLeadSlots=slots,
            count=len(group),
            rate=len(group) / sample_size,
        )
        for slots, group in sorted(
            lead_groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]
    lead_results = [
        LeadResult(
            leadId=_lead_id(slots),
            opponentLeadSlots=slots,
            sampleSize=len(group),
            wins=sum(1 for record in group if record.outcome == "win"),
            losses=sum(1 for record in group if record.outcome == "loss"),
            draws=sum(1 for record in group if record.outcome == "draw"),
            winRate=(sum(1 for record in group if record.outcome == "win") / len(group)),
        )
        for slots, group in sorted(
            lead_groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]
    threats = _compute_threats(records)
    our_damage = _compute_our_damage(records)
    quality = StatisticsQuality(
        unattributedDamageEvents=sum(record.captureQuality.unattributedDamageEvents for record in records),
        roundedHpBattles=sum(1 for record in records if record.captureQuality.roundedHp),
        damageEventsConsidered=sum(len(record.damageEvents) for record in records),
        lossesConsidered=losses,
    )
    return DStatistics(
        outcomes=OutcomeCounts(
            wins=wins,
            losses=losses,
            draws=draws,
            sampleSize=sample_size,
            winRate=wins / sample_size,
        ),
        leads=leads,
        leadResults=lead_results,
        threatsInLosses=threats,
        ourDamage=our_damage,
        quality=quality,
    )


def _compute_threats(records: list[NormalizedDBattle]) -> list[ThreatStat]:
    losses = [record for record in records if record.outcome == "loss"]
    if not losses:
        return []
    by_slot: dict[int, dict[str, float | int]] = {}
    for record in losses:
        battle_damage_by_slot: dict[int, float] = defaultdict(float)
        battle_ko_by_slot: dict[int, int] = defaultdict(int)
        for event in record.damageEvents:
            if not event.direct or not event.attributed or event.targetSubstitute:
                continue
            if event.target.side != "ours" or event.source is None or event.source.side != "opponent":
                continue
            battle_damage_by_slot[event.source.slot] += event.hpPercentLoss
            if event.causedKo:
                battle_ko_by_slot[event.source.slot] += 1
        for slot in record.opponentSelectedSlots:
            stats = by_slot.setdefault(
                slot,
                {
                    "selectedCount": 0,
                    "enteredCount": 0,
                    "damageBattleCount": 0,
                    "directKoCount": 0,
                    "directDamagePercent": 0.0,
                },
            )
            stats["selectedCount"] += 1
            if slot in record.enteredSlots["opponent"]:
                stats["enteredCount"] += 1
            damage = battle_damage_by_slot.get(slot, 0.0)
            if damage > 0:
                stats["damageBattleCount"] += 1
                stats["directDamagePercent"] += damage
            stats["directKoCount"] += battle_ko_by_slot.get(slot, 0)
    rows = [
        ThreatStat(
            pokemon=PokemonRef(side="opponent", slot=slot),
            lossSampleSize=len(losses),
            selectedCount=int(values["selectedCount"]),
            enteredCount=int(values["enteredCount"]),
            damageBattleCount=int(values["damageBattleCount"]),
            directKoCount=int(values["directKoCount"]),
            directDamagePercent=float(values["directDamagePercent"]),
        )
        for slot, values in by_slot.items()
    ]
    rows.sort(
        key=lambda row: (
            -row.directDamagePercent,
            -row.damageBattleCount,
            -row.selectedCount,
            row.pokemon.slot,
        )
    )
    return rows


def _compute_our_damage(records: list[NormalizedDBattle]) -> list[OurDamageStat]:
    sample_size = len(records)
    our_slots = records[0].ourFourSlots
    totals = {slot: 0.0 for slot in our_slots}
    for record in records:
        for event in record.damageEvents:
            if not event.direct or not event.attributed or event.targetSubstitute:
                continue
            if event.target.side != "opponent" or event.source is None or event.source.side != "ours":
                continue
            if event.source.slot in totals:
                totals[event.source.slot] += event.hpPercentLoss
    rows = [
        OurDamageStat(
            pokemon=PokemonRef(side="ours", slot=slot),
            sampleSize=sample_size,
            totalDirectDamagePercent=totals[slot],
            averageDirectDamagePercent=(totals[slot] / sample_size),
        )
        for slot in our_slots
    ]
    rows.sort(key=lambda row: (-row.averageDirectDamagePercent, row.pokemon.slot))
    return rows


def _lead_id(slots: tuple[int, int]) -> str:
    return f"lead-{slots[0]}-{slots[1]}"
