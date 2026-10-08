"""Aggregate observed player counters without treating missing values as zero."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

STAT_LABELS = {
    "score": "Points",
    "goals": "Buts",
    "assists": "Passes décisives",
    "saves": "Arrêts",
    "shots": "Tirs",
    "demos": "Démolitions",
    "touches": "Touches de balle",
    "car_touches": "Contacts voitures",
}


class StatRow(Protocol):
    """Read counters from database rows or deterministic in-memory observations."""

    def __getitem__(self, key: str) -> int | None: ...


@dataclass(frozen=True)
class StatTotal:
    """A total and its actual sample size, including received zeroes."""

    total: int | None
    matches: int

    @property
    def average(self) -> float | None:
        """Return a per-match mean using only games with this counter available."""
        if self.total is None or self.matches == 0:
            return None
        return self.total / self.matches


def aggregate_statistics(rows: Sequence[StatRow]) -> dict[str, StatTotal]:
    """Sum the selected player's last observed counters across the given matches."""
    statistics = {}
    for field in STAT_LABELS:
        values = [row[field] for row in rows if row[field] is not None]
        total = None
        if values:
            total = sum(values)
        statistics[field] = StatTotal(total, len(values))
    return statistics
