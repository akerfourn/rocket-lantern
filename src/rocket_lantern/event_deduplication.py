"""Read-only filtering of exact, closely repeated positioned API events."""

import json
from collections import deque
from collections.abc import Hashable, Mapping, Sequence
from datetime import datetime, timedelta
from sqlite3 import Row

from rocket_lantern.event_data import integer, number

type EventRow = Row | Mapping[str, object]

DUPLICATE_WINDOW = timedelta(milliseconds=100)
MAX_RECENT_EVENTS = 32
EVENT_IDENTITY_FIELDS = (
    "match_id",
    "kind",
    "source_event",
    "origin",
    "actor_id",
    "secondary_id",
    "team",
    "speed",
    "round_seconds",
    "position_subject",
)
PARTICIPANT_IDENTITY_FIELDS = ("role", "player_id", "name", "team", "shortcut")


class RecentEventDeduplicator:
    """Keep a bounded, short-lived identity cache, not a match-long event history."""

    def __init__(self) -> None:
        self._recent: deque[tuple[Hashable, datetime]] = deque(maxlen=MAX_RECENT_EVENTS)

    def clear(self) -> None:
        self._recent.clear()

    def is_duplicate(self, signature: Hashable | None, observed_at: str) -> bool:
        """Remember an occurrence and recognize exact repeats in the rolling window."""
        if signature is None:
            return False
        timestamp = datetime.fromisoformat(observed_at)
        while self._recent and timestamp - self._recent[0][1] > DUPLICATE_WINDOW:
            self._recent.popleft()
        duplicate = False
        for previous, previous_at in self._recent:
            elapsed = timestamp - previous_at
            if signature == previous and timedelta(0) <= elapsed <= DUPLICATE_WINDOW:
                duplicate = True
                break
        self._recent.append((signature, timestamp))
        return duplicate


def _value(row: EventRow, field: str) -> object:
    if field in row.keys():
        return row[field]
    return None


def positioned_event_signature(row: EventRow, participants: Sequence[EventRow]) -> str | None:
    """Compare full received positions, measurements and every participant, not row IDs."""
    if _value(row, "origin") not in (None, "api"):
        return None
    x = number(_value(row, "x"))
    y = number(_value(row, "y"))
    z = number(_value(row, "z"))
    if x is None or y is None or z is None:
        return None
    identity = {field: _value(row, field) for field in EVENT_IDENTITY_FIELDS}
    identity["position"] = (x, y, z)
    details = _value(row, "details_json")
    identity["details"] = json.loads(details) if isinstance(details, str) else details
    for field in ("actor", "secondary"):
        if identity[f"{field}_id"] is None:
            identity[f"{field}_name"] = _value(row, f"{field}_name")
    hints = []
    for participant in participants:
        values = [_value(participant, field) for field in PARTICIPANT_IDENTITY_FIELDS]
        hints.append(json.dumps(values, ensure_ascii=True))
    identity["participants"] = sorted(hints)
    return json.dumps(identity, sort_keys=True, ensure_ascii=True)


def visible_events(rows: Sequence[EventRow], participants: Sequence[EventRow]) -> list[EventRow]:
    """Filter chronologically ordered display rows without changing stored occurrences."""
    references: dict[int, list[EventRow]] = {}
    for participant in participants:
        event_id = integer(_value(participant, "event_id"))
        if event_id is not None:
            references.setdefault(event_id, []).append(participant)
    deduplicator = RecentEventDeduplicator()
    visible = []
    for row in rows:
        observed_at = _value(row, "observed_at")
        event_id = integer(_value(row, "id"))
        refs = []
        if event_id is not None:
            refs = references.get(event_id, [])
        signature = positioned_event_signature(row, refs)
        if isinstance(observed_at, str) and deduplicator.is_duplicate(signature, observed_at):
            continue
        visible.append(row)
    return visible
