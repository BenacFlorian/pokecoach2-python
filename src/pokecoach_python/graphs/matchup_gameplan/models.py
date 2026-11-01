"""Typed models for Phase E synthesis sources and outputs."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PokemonRef(StrictModel):
    side: Literal["ours", "opponent"]
    slot: int = Field(ge=0, le=5)


class PokemonHighlight(StrictModel):
    pokemon: PokemonRef
    explanation: str = Field(min_length=1, max_length=700)


class StrategyGameplan(StrictModel):
    opening: str = Field(min_length=1, max_length=700)
    midgame: str = Field(min_length=1, max_length=700)
    endgame: str = Field(min_length=1, max_length=700)
    threats: list[PokemonHighlight] = Field(min_length=1, max_length=2)
    strengths: list[PokemonHighlight] = Field(min_length=1, max_length=2)
    evidenceBattleIds: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lists(self) -> StrategyGameplan:
        if len(set(self.evidenceBattleIds)) != len(self.evidenceBattleIds):
            raise ValueError("gameplan evidenceBattleIds must be unique")
        threat_refs = {(item.pokemon.side, item.pokemon.slot) for item in self.threats}
        strength_refs = {(item.pokemon.side, item.pokemon.slot) for item in self.strengths}
        if len(threat_refs) != len(self.threats):
            raise ValueError("gameplan threats must reference distinct pokemon")
        if len(strength_refs) != len(self.strengths):
            raise ValueError("gameplan strengths must reference distinct pokemon")
        if any(item.pokemon.side != "opponent" for item in self.threats):
            raise ValueError("gameplan threats must reference opponent pokemon")
        if any(item.pokemon.side != "ours" for item in self.strengths):
            raise ValueError("gameplan strengths must reference our pokemon")
        return self


class StrategyWinCondition(StrictModel):
    description: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=1000)
    evidenceBattleIds: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> StrategyWinCondition:
        if len(set(self.evidenceBattleIds)) != len(self.evidenceBattleIds):
            raise ValueError("win condition evidenceBattleIds must be unique")
        return self


class StrategyOutput(StrictModel):
    gameplan: StrategyGameplan
    winCondition: StrategyWinCondition


class BattleDamageEvent(StrictModel):
    turn: int = Field(ge=1)
    source: PokemonRef | None = None
    target: PokemonRef
    direct: bool = True
    attributed: bool = True
    causedKo: bool = False
    targetSubstitute: bool = False
    hpPercentLoss: float = Field(ge=0.0)
    cause: str | None = None


class BattleCaptureQuality(StrictModel):
    exactHp: bool = False
    roundedHp: bool = False
    unattributedDamageEvents: int = Field(default=0, ge=0)


class NormalizedDBattle(StrictModel):
    battleId: str
    sampleKey: str
    sha256: str
    outcome: Literal["win", "loss", "draw"]
    opponentLeadSlots: tuple[int, int]
    ourFourSlots: tuple[int, int, int, int]
    ourLeadSlots: tuple[int, int]
    opponentSelectedSlots: tuple[int, int, int, int]
    enteredSlots: dict[str, tuple[int, ...]]
    survivorSlots: dict[str, tuple[int, ...]]
    turnCount: int = Field(ge=1)
    turns: list[dict[str, Any]]
    damageEvents: list[BattleDamageEvent]
    captureQuality: BattleCaptureQuality


class SelectionBucket(StrictModel):
    requested: int = Field(ge=0)
    retainedBattleIds: list[str]
    retainedBattleDigests: list[str]
    shortfallReason: str | None = None


class SelectionManifest(StrictModel):
    populationSize: int = Field(ge=0)
    quotas: dict[str, int]
    close: SelectionBucket
    wins: SelectionBucket
    losses: SelectionBucket
    selectedBattleIds: list[str]
    limitations: list[str] = Field(default_factory=list)


class OutcomeCounts(StrictModel):
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    draws: int = Field(ge=0)
    sampleSize: int = Field(ge=0)
    winRate: float = Field(ge=0.0, le=1.0)


class LeadFrequency(StrictModel):
    leadId: str
    opponentLeadSlots: tuple[int, int]
    count: int = Field(ge=0)
    rate: float = Field(ge=0.0, le=1.0)


class LeadResult(StrictModel):
    leadId: str
    opponentLeadSlots: tuple[int, int]
    sampleSize: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    draws: int = Field(ge=0)
    winRate: float = Field(ge=0.0, le=1.0)


class ThreatStat(StrictModel):
    pokemon: PokemonRef
    lossSampleSize: int = Field(ge=0)
    selectedCount: int = Field(ge=0)
    enteredCount: int = Field(ge=0)
    damageBattleCount: int = Field(ge=0)
    directKoCount: int = Field(ge=0)
    directDamagePercent: float = Field(ge=0.0)


class OurDamageStat(StrictModel):
    pokemon: PokemonRef
    sampleSize: int = Field(ge=0)
    totalDirectDamagePercent: float = Field(ge=0.0)
    averageDirectDamagePercent: float = Field(ge=0.0)


class StatisticsQuality(StrictModel):
    unattributedDamageEvents: int = Field(ge=0)
    roundedHpBattles: int = Field(ge=0)
    damageEventsConsidered: int = Field(ge=0)
    lossesConsidered: int = Field(ge=0)


class DStatistics(StrictModel):
    outcomes: OutcomeCounts
    leads: list[LeadFrequency]
    leadResults: list[LeadResult]
    threatsInLosses: list[ThreatStat]
    ourDamage: list[OurDamageStat]
    quality: StatisticsQuality


class TeamPokemonContext(StrictModel):
    side: Literal["ours", "opponent"]
    slot: int = Field(ge=0, le=5)
    species: str
    item: str | None = None
    ability: str | None = None
    moves: tuple[str, ...] = ()


class PreparedSources(StrictModel):
    sourceHash: str
    tokenEstimate: int = Field(ge=0)
    tokenBudget: int = Field(ge=1)
    outputTokenBudget: int = Field(ge=0)
    modelName: str
    manifest: SelectionManifest
    statistics: DStatistics
    selectedBattles: list[NormalizedDBattle]
    ourTeam: list[TeamPokemonContext]
    opponentTeam: list[TeamPokemonContext]
    limitations: list[str] = Field(default_factory=list)


def compute_sources_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


def validate_strategy_against_sources(
    strategy: StrategyOutput,
    sources: PreparedSources,
) -> StrategyOutput:
    selected_ids = {battle.battleId for battle in sources.selectedBattles}
    if not selected_ids:
        raise ValueError("prepared sources require selected battles")
    our_slots = set(sources.selectedBattles[0].ourFourSlots)
    opponent_slots = {
        slot for battle in sources.selectedBattles for slot in battle.opponentSelectedSlots
    }
    for name, ids in (
        ("gameplan", strategy.gameplan.evidenceBattleIds),
        ("winCondition", strategy.winCondition.evidenceBattleIds),
    ):
        if unknown := sorted(set(ids) - selected_ids):
            raise ValueError(f"{name} cites unknown battle ids: {unknown}")
    for item in strategy.gameplan.strengths:
        if item.pokemon.slot not in our_slots:
            raise ValueError("strengths must reference our fixed four")
    for item in strategy.gameplan.threats:
        if item.pokemon.slot not in opponent_slots:
            raise ValueError("threats must reference opponent pokemon seen in selected logs")
    return strategy
