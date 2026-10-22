"""Read-only positioned events and deterministic player colors for the match map."""

from collections.abc import Mapping, Sequence
from colorsys import hls_to_rgb
from dataclasses import dataclass, replace
from sqlite3 import Row

from rocket_lantern.event_data import integer, number

type EventRow = Row | Mapping[str, object]
type Position = tuple[float, float, float]

PLAYER_COLORS = (
    "#56b4e9",
    "#e69f00",
    "#71d4a6",
    "#e67da9",
    "#b3a0ef",
    "#f0d35e",
    "#6cd5d0",
    "#f28e79",
)
UNKNOWN_COLOR = "#a8afb8"


@dataclass(frozen=True)
class MapEvent:
    """A stored occurrence with genuine coordinates, not an inferred car location."""

    event_id: int
    kind: str
    position: Position
    time_seconds: int | None
    overtime: bool
    actor_key: str | None
    actor_name: str | None
    participant_names: tuple[str, ...]
    position_subject: str | None
    color: str = UNKNOWN_COLOR
    actor_team: int | None = None


def positioned_events(
    rows: Sequence[EventRow], participants: Sequence[EventRow]
) -> tuple[MapEvent, ...]:
    """Discard incomplete coordinates and keep unresolved identities visibly separate."""
    references: dict[int, list[EventRow]] = {}
    for participant in participants:
        event_id = integer(participant["event_id"])
        if event_id is not None:
            references.setdefault(event_id, []).append(participant)
    points = []
    for row in rows:
        x, y, z = (number(row[key]) for key in ("x", "y", "z"))
        event_id = integer(row["id"])
        if event_id is None or x is None or y is None or z is None:
            continue
        refs = references.get(event_id, [])
        actor_key, actor_name, actor_team = _actor(row, refs)
        names = []
        for reference in refs:
            name = _name(reference["name"])
            if name is not None and name not in names:
                names.append(name)
        points.append(
            MapEvent(
                event_id,
                str(row["kind"]),
                (x, y, z),
                integer(row["time_seconds"]),
                row["overtime"] == 1,
                actor_key,
                actor_name,
                tuple(names),
                _name(row["position_subject"]),
                actor_team=actor_team,
            )
        )
    colors = _player_colors(points)
    return tuple(
        replace(point, color=colors.get(point.actor_key, UNKNOWN_COLOR)) for point in points
    )


def _name(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _team(value: object) -> int | None:
    team = integer(value)
    if team in (0, 1):
        return team
    return None


def _actor(
    row: EventRow, references: Sequence[EventRow]
) -> tuple[str | None, str | None, int | None]:
    actor_id = integer(row["actor_id"])
    actor_name = _name(row["actor_name"])
    if actor_id is not None:
        actor_team = None
        if "actor_team" in row.keys():
            actor_team = _team(row["actor_team"])
        for reference in references:
            if reference["player_id"] == actor_id:
                actor_name = _name(reference["name"]) or actor_name
                if reference["team"] is not None:
                    actor_team = _team(reference["team"])
                break
        return f"player:{actor_id}", actor_name, actor_team
    roles = {
        "GoalScored": "scorer",
        "CrossbarHit": "last_touch",
        "BallHit": "hitter",
        "BoostPickup": "collector",
    }
    role = roles.get(str(row["kind"]), "actor")
    for reference in references:
        if reference["role"] != role:
            continue
        name = _name(reference["name"])
        player_id = integer(reference["player_id"])
        team = integer(reference["team"])
        if player_id is not None:
            return f"player:{player_id}", name, _team(team)
        shortcut = integer(reference["shortcut"])
        if name is not None and team is not None and shortcut is not None:
            # This is a match-local visual key, never a database identity link.
            return f"hint:{team}:{shortcut}:{name}", name, _team(team)
        return None, name, _team(team)
    return None, actor_name, None


def _player_colors(points: Sequence[MapEvent]) -> dict[str | None, str]:
    keys = sorted({point.actor_key for point in points if point.actor_key is not None})
    colors: dict[str | None, str] = {}
    for index, key in enumerate(keys):
        if index < len(PLAYER_COLORS):
            colors[key] = PLAYER_COLORS[index]
        else:
            # Additional players keep unique hues without a random seed or saved preference.
            hue = (index * 137) % 360
            red, green, blue = hls_to_rgb(hue / 360, 0.65, 0.65)
            colors[key] = f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
    return colors
