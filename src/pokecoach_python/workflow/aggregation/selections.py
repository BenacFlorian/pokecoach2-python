"""Deterministic lead-pick aggregation for phase C."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.schemas.analysis_result import (
    FourFrequency,
    LeadPickSamplingDiagnostics,
    LeadPickSection,
    LeadSelection,
    OpponentLeadEntry,
    OpponentLeadsSection,
    SelectionFrequency,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.battle_records import canonical_four, four_slots_leads_first


@dataclass(frozen=True)
class _CandidateKey:
    our_four: tuple[int, int, int, int]
    our_lead: tuple[int, int]


@dataclass
class _OutcomeBucket:
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def sample_size(self) -> int:
        return self.wins + self.losses + self.draws

    def win_rate(self) -> Fraction | None:
        if self.sample_size == 0:
            return None
        return Fraction(self.wins, self.sample_size)


def studied_opponent_leads(
    section: OpponentLeadsSection,
    *,
    top_n: int = 3,
) -> list[OpponentLeadEntry]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    return list(section.leads[: min(top_n, len(section.leads))])


def _candidate_key(record: BattleRecord) -> _CandidateKey:
    four_raw = record.participants["ourFourSlots"]
    lead_raw = record.participants["ourLeadSlots"]
    four = canonical_four((int(four_raw[0]), int(four_raw[1]), int(four_raw[2]), int(four_raw[3])))
    lead = canonical_lead((int(lead_raw[0]), int(lead_raw[1])))
    return _CandidateKey(our_four=four, our_lead=lead)


def _lead_id_for_battle(
    record: BattleRecord,
    leads_by_slots: dict[tuple[int, int], str],
) -> str:
    key = canonical_lead(record.preview.opponent_lead_slots)
    if key not in leads_by_slots:
        raise ValueError("battle opponent lead unknown in phase A section")
    return leads_by_slots[key]


def _apply_outcome(bucket: _OutcomeBucket, outcome: str) -> None:
    if outcome == "win":
        bucket.wins += 1
    elif outcome == "loss":
        bucket.losses += 1
    elif outcome == "draw":
        bucket.draws += 1
    else:
        raise ValueError("non-terminal outcome in aggregation")


def _lead_weights(studied: Sequence[OpponentLeadEntry]) -> dict[str, Fraction]:
    total = sum(entry.count for entry in studied)
    if total <= 0:
        raise ValueError("studied leads require positive A counts")
    return {entry.id: Fraction(entry.count, total) for entry in studied}


def _weighted_win_rate(
    candidate: _CandidateKey,
    studied_ids: Sequence[str],
    weights: dict[str, Fraction],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
) -> Fraction | None:
    per_lead = stats.get(candidate, {})
    total_weight = Fraction(0)
    weighted_sum = Fraction(0)
    for lid in studied_ids:
        bucket = per_lead.get(lid)
        if bucket is None or bucket.sample_size == 0:
            continue
        rate = bucket.win_rate()
        assert rate is not None
        w = weights[lid]
        weighted_sum += w * rate
        total_weight += w
    if total_weight == 0:
        return None
    return weighted_sum / total_weight


def _coverage_weight(
    candidate: _CandidateKey,
    studied_ids: Sequence[str],
    weights: dict[str, Fraction],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
) -> Fraction:
    per_lead = stats.get(candidate, {})
    covered = Fraction(0)
    for lid in studied_ids:
        bucket = per_lead.get(lid)
        if bucket is not None and bucket.sample_size > 0:
            covered += weights[lid]
    return covered


def _total_sample(
    candidate: _CandidateKey,
    studied_ids: Sequence[str],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
) -> int:
    per_lead = stats.get(candidate, {})
    return sum(
        per_lead[lid].sample_size
        for lid in studied_ids
        if lid in per_lead and per_lead[lid].sample_size > 0
    )


def _rank_candidates(
    candidates: Sequence[_CandidateKey],
    studied_ids: Sequence[str],
    weights: dict[str, Fraction],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
) -> list[_CandidateKey]:
    full_coverage = [
        c
        for c in candidates
        if _coverage_weight(c, studied_ids, weights, stats) == 1
    ]
    pool = full_coverage if full_coverage else list(candidates)

    def sort_key(candidate: _CandidateKey) -> tuple:
        full = candidate in full_coverage
        cov = _coverage_weight(candidate, studied_ids, weights, stats)
        rate = _weighted_win_rate(candidate, studied_ids, weights, stats)
        rate_key = rate if rate is not None else Fraction(-1)
        sample = _total_sample(candidate, studied_ids, stats)
        return (
            0 if full else 1,
            -cov,
            -rate_key,
            -sample,
            candidate.our_four,
            candidate.our_lead,
        )

    return sorted(pool, key=sort_key)


def _build_comparisons(
    candidates: Sequence[_CandidateKey],
    studied: Sequence[OpponentLeadEntry],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        per_lead = stats.get(candidate, {})
        for entry in studied:
            bucket = per_lead.get(entry.id)
            if bucket is None or bucket.sample_size == 0:
                continue
            display_four = four_slots_leads_first(candidate.our_four, candidate.our_lead)
            rows.append(
                {
                    "opponentLeadId": entry.id,
                    "ourFourSlots": list(display_four),
                    "ourLeadSlots": list(candidate.our_lead),
                    "wins": bucket.wins,
                    "losses": bucket.losses,
                    "draws": bucket.draws,
                    "sampleSize": bucket.sample_size,
                }
            )
    return rows


def _build_sampling_diagnostics(
    battles: Sequence[BattleRecord],
    studied_ids: Sequence[str],
    leads_by_slots: dict[tuple[int, int], str],
) -> LeadPickSamplingDiagnostics:
    studied_set = set(studied_ids)
    four_counts: Counter[tuple[int, int, int, int]] = Counter()
    selection_counts: Counter[tuple[tuple[int, int, int, int], tuple[int, int]]] = Counter()
    sample_size = 0
    for battle in battles:
        lid = _lead_id_for_battle(battle, leads_by_slots)
        if lid not in studied_set:
            continue
        sample_size += 1
        key = _candidate_key(battle)
        four_counts[key.our_four] += 1
        selection_counts[(key.our_four, key.our_lead)] += 1

    if sample_size == 0:
        raise ValueError("no battles for sampling diagnostics")

    four_rows = [
        FourFrequency(ourFourSlots=four, count=count)
        for four, count in sorted(
            four_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    selection_rows = [
        SelectionFrequency(
            selection=LeadSelection(
                ourFourSlots=four_slots_leads_first(four, lead),
                ourLeadSlots=lead,
            ),
            count=count,
        )
        for (four, lead), count in sorted(
            selection_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ]
    return LeadPickSamplingDiagnostics(
        source="policy-samples",
        samplingPolicy="stochastic-team-preview-v1",
        sampleSize=sample_size,
        uniqueFours=len(four_rows),
        uniqueSelections=len(selection_rows),
        fourFrequencies=four_rows,
        selectionFrequencies=selection_rows,
    )


def _build_limitations(
    selection: _CandidateKey,
    studied: Sequence[OpponentLeadEntry],
    weights: dict[str, Fraction],
    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]],
    rule_version: str,
    *,
    sampling: LeadPickSamplingDiagnostics | None = None,
) -> list[str]:
    cov = _coverage_weight(selection, [e.id for e in studied], weights, stats)
    total_n = _total_sample(selection, [e.id for e in studied], stats)
    rate = _weighted_win_rate(selection, [e.id for e in studied], weights, stats)
    rate_txt = f"{float(rate * 100):.2f}%" if rate is not None else "indisponible"
    lines = [
        (
            f"Recommandation empirique ({rule_version}) : règle de couverture complète "
            f"puis taux pondéré par les fréquences A du top étudié."
        ),
        f"Couverture pondérée des leads étudiés : {float(cov * 100):.0f}%.",
        f"Taux de victoire pondéré observé : {rate_txt} sur {total_n} combats terminés.",
    ]
    if cov < 1:
        lines.append(
            "Couverture incomplète : la sélection ne confronte pas tous les leads retenus "
            "avec le même effectif."
        )
    if total_n < 30:
        lines.append("Effectifs faibles : interpréter la recommandation avec prudence.")
    if sampling is not None and sampling.uniqueFours == 1:
        lines.append(
            "La policy n'a échantillonné qu'un seul quatre sur "
            f"{sampling.sampleSize} combats de phase C ; aucune composition alternative "
            "n'a pu être comparée."
        )
    return lines


def aggregate_selections(
    battles: Sequence[BattleRecord],
    leads: OpponentLeadsSection,
    *,
    rule_version: str = "selection-v1",
    top_n: int = 3,
) -> LeadPickSection:
    studied = studied_opponent_leads(leads, top_n=top_n)
    if not studied:
        raise ValueError("no opponent leads to study")
    leads_by_slots = {canonical_lead(entry.slots): entry.id for entry in leads.leads}
    weights = _lead_weights(studied)
    studied_ids = [entry.id for entry in studied]

    stats: dict[_CandidateKey, dict[str, _OutcomeBucket]] = defaultdict(
        lambda: defaultdict(_OutcomeBucket)
    )
    candidates_set: set[_CandidateKey] = set()
    for battle in battles:
        cid = _lead_id_for_battle(battle, leads_by_slots)
        if cid not in studied_ids:
            continue
        key = _candidate_key(battle)
        candidates_set.add(key)
        _apply_outcome(stats[key][cid], battle.outcome)

    if not candidates_set:
        raise ValueError("no candidate observations for studied leads")

    ranked = _rank_candidates(list(candidates_set), studied_ids, weights, stats)
    winner = ranked[0]
    comparisons = _build_comparisons(ranked, studied, stats)
    sampling = _build_sampling_diagnostics(battles, studied_ids, leads_by_slots)
    limitations = _build_limitations(
        winner, studied, weights, stats, rule_version, sampling=sampling
    )

    winner_four = four_slots_leads_first(winner.our_four, winner.our_lead)
    return LeadPickSection(
        selection=LeadSelection(
            ourFourSlots=winner_four,
            ourLeadSlots=winner.our_lead,
        ),
        comparisons=comparisons,
        selectionRuleVersion=rule_version,
        limitations=limitations,
        samplingDiagnostics=sampling,
    )
