"""Index event roles and families for read-only, identity-based display filters."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rocket_lantern.event_data import integer
from rocket_lantern.event_deduplication import EventRow
from rocket_lantern.i18n import text as T

type PlayerFilter = int | Literal["unidentified"] | None

FAMILY_LABELS = {
    "goals": T("Buts et passes"),
    "saves_shots": T("Tirs et arrêts"),
    "demolitions": T("Démolitions"),
    "ball_hits": T("Touches de balle"),
    "posts": T("Poteaux"),
    "boost": T("Boost"),
    "states": T("États des joueurs"),
    "presence": T("Arrivées et départs"),
    "match": T("Déroulement du match"),
    "statistics": T("Autres statistiques"),
    "other": T("Autres événements"),
}
ACTOR_ROLES = frozenset({"scorer", "actor", "hitter", "collector", "player"})
TARGET_ROLES = frozenset({"assister", "target"})


def event_family(kind: str) -> str:
    if kind in ("GoalScored", "Stat:Goal", "Stat:Assist"):
        return "goals"
    if kind in ("Stat:Shot", "Stat:Save", "Stat:EpicSave"):
        return "saves_shots"
    if kind == "Stat:Demolish":
        return "demolitions"
    if kind == "BallHit":
        return "ball_hits"
    if kind == "CrossbarHit":
        return "posts"
    if kind == "BoostPickup":
        return "boost"
    if kind.startswith("PlayerState:"):
        return "states"
    if kind in ("PlayerJoined", "PlayerLeft"):
        return "presence"
    if kind.startswith(("Match", "GoalReplay", "Clock", "Round", "Countdown", "Podium")):
        return "match"
    if kind.startswith("Stat:") or kind == "StatfeedEvent":
        return "statistics"
    return "other"


@dataclass(frozen=True)
class EventRoles:
    event_id: int
    family: str
    actors: frozenset[int]
    targets: frozenset[int]


def _players(
    row: EventRow, references: Sequence[EventRow], field: str, roles: frozenset[str]
) -> frozenset[int]:
    players = set()
    direct = integer(row[field])
    if direct is not None:
        players.add(direct)
    for reference in references:
        identifier = integer(reference["player_id"])
        if reference["role"] in roles and identifier is not None:
            players.add(identifier)
    return frozenset(players)


def _matches(selection: PlayerFilter, players: frozenset[int]) -> bool:
    if selection is None:
        return True
    if selection == "unidentified":
        return not players
    return selection in players


class EventFilterIndex:
    """Precompute roles once; filtering never reloads or modifies stored events."""

    def __init__(self, rows: Sequence[EventRow], participants: Sequence[EventRow]) -> None:
        references: dict[int, list[EventRow]] = {}
        for participant in participants:
            references.setdefault(participant["event_id"], []).append(participant)
        self.events = tuple(self._roles(row, references.get(row["id"], [])) for row in rows)
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.family] = counts.get(event.family, 0) + 1
        self.families = {key: counts[key] for key in FAMILY_LABELS if key in counts}

    @staticmethod
    def _roles(row: EventRow, references: Sequence[EventRow]) -> EventRoles:
        roles = ACTOR_ROLES
        if row["kind"] == "CrossbarHit":
            roles = frozenset({"last_touch"})
        return EventRoles(
            row["id"],
            event_family(str(row["kind"])),
            _players(row, references, "actor_id", roles),
            _players(row, references, "secondary_id", TARGET_ROLES),
        )

    def select(
        self, actor: PlayerFilter, target: PlayerFilter, families: frozenset[str]
    ) -> frozenset[int]:
        return frozenset(
            event.event_id
            for event in self.events
            if event.family in families
            and _matches(actor, event.actors)
            and _matches(target, event.targets)
        )
