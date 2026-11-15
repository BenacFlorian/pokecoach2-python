"""Limit DB write frequency during long simulation runs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.simulation_budgets import (
    BATTLE_INSERT_BATCH_C,
    BATTLE_INSERT_BATCH_D,
    PROGRESS_UPDATE_BATCH_A,
    PROGRESS_UPDATE_BATCH_B,
    PROGRESS_UPDATE_BATCH_C,
    PROGRESS_UPDATE_BATCH_D,
)

ProgressCallback = Callable[[str, int, int], None]
InsertBattleFn = Callable[[BattleRecord, str], str]


def should_report_progress(done: int, total: int, batch_size: int) -> bool:
    if batch_size <= 0:
        return True
    if done <= 0:
        return True
    if done >= total:
        return True
    return done % batch_size == 0


def report_progress_batched(
    callback: ProgressCallback,
    phase: str,
    done: int,
    total: int,
    batch_size: int,
) -> None:
    if should_report_progress(done, total, batch_size):
        callback(phase, done, total)


@dataclass
class _BufferedBattle:
    record: BattleRecord
    sample_key: str


@dataclass
class BattleInsertBatcher:
    """Buffer battle inserts and flush in one DB transaction per batch."""

    insert_batch: Callable[[list[tuple[BattleRecord, str]]], list[str]]
    batch_size: int
    _pending: list[_BufferedBattle] = field(default_factory=list)
    _returned_ids: list[str] = field(default_factory=list)

    def add(self, record: BattleRecord, sample_key: str) -> str:
        self._pending.append(_BufferedBattle(record=record, sample_key=sample_key))
        if len(self._pending) >= self.batch_size:
            self._flush_pending()
        if self._returned_ids:
            return self._returned_ids[-1]
        return f"pending:{sample_key}"

    def flush(self) -> list[str]:
        if self._pending:
            self._flush_pending()
        return list(self._returned_ids)

    def all_ids(self) -> Sequence[str]:
        return self._returned_ids

    def _flush_pending(self) -> None:
        batch = [(item.record, item.sample_key) for item in self._pending]
        self._pending.clear()
        ids = self.insert_batch(batch)
        self._returned_ids.extend(ids)


def batch_insert_wrapper(
    insert_batch: Callable[[list[tuple[BattleRecord, str]]], list[str]],
    batch_size: int,
) -> tuple[Callable[[BattleRecord, str], str], Callable[[], None]]:
    batcher = BattleInsertBatcher(insert_batch=insert_batch, batch_size=batch_size)

    def insert_one(record: BattleRecord, sample_key: str) -> str:
        return batcher.add(record, sample_key)

    def finalize() -> None:
        batcher.flush()

    return insert_one, finalize


# Defaults re-exported for phases
PHASE_A_PROGRESS_BATCH = PROGRESS_UPDATE_BATCH_A
PHASE_B_PROGRESS_BATCH = PROGRESS_UPDATE_BATCH_B
PHASE_C_PROGRESS_BATCH = PROGRESS_UPDATE_BATCH_C
PHASE_D_PROGRESS_BATCH = PROGRESS_UPDATE_BATCH_D
PHASE_C_INSERT_BATCH = BATTLE_INSERT_BATCH_C
PHASE_D_INSERT_BATCH = BATTLE_INSERT_BATCH_D