"""Compact event records, independent of storage and the user interface."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

type Measurement = str | int | float | bool | None


def integer(value: object) -> int | None:
    """Accept nonnegative counters, excluding booleans."""
    if type(value) is int and value >= 0:
        return value
    return None


def number(value: object) -> float | None:
    """Accept finite numeric measurements, excluding booleans."""
    if type(value) in (int, float) and math.isfinite(value):
        return float(value)
    return None


@dataclass
class EventParticipant:
    """Keep explicit identity hints when a permanent player link is unavailable."""

    role: str
    primary_id: str | None
    name: str | None
    team: int | None
    shortcut: int | None


@dataclass
class MatchEvent:
    """Selected event fields; missing measurements never become zero."""

    kind: str
    observed_at: str
    time_seconds: int | None
    overtime: bool | None
    actor: str | None = None
    secondary: str | None = None
    team: int | None = None
    speed: float | None = None
    round_seconds: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    fingerprint: str = ""
    source_event: str = ""
    origin: str = "api"
    position_subject: str | None = None
    details: dict[str, Measurement] = field(default_factory=dict)
    participants: list[EventParticipant] = field(default_factory=list)


def extract_event(
    kind: str,
    data: dict[str, object],
    observed_at: str,
    time_seconds: int | None,
    overtime: bool | None,
    resolve: Callable[[object], str | None],
) -> MatchEvent:
    """Extract a documented event without retaining its raw API payload."""
    event = MatchEvent(kind, observed_at, time_seconds, overtime, source_event=kind)
    event_time = integer(data.get("TimeSeconds"))
    if event_time is not None:
        event.time_seconds = event_time
    if type(data.get("bOvertime")) is bool:
        event.overtime = data["bOvertime"]
    actors, location = _event_fields(event, data)
    for role, actor in actors:
        if not isinstance(actor, dict):
            continue
        name = actor.get("Name", actor.get("PlayerName"))
        if not isinstance(name, str):
            name = None
        event.participants.append(
            EventParticipant(
                role,
                resolve(actor),
                name,
                integer(actor.get("TeamNum")),
                integer(actor.get("Shortcut")),
            )
        )
    primary_roles = {"scorer", "actor", "hitter", "collector", "player"}
    if kind == "CrossbarHit":
        primary_roles = {"last_touch"}
    for participant in event.participants:
        if participant.role in primary_roles:
            event.actor = participant.primary_id
            event.team = participant.team
            break
    for participant in event.participants:
        if participant.role in ("assister", "target"):
            event.secondary = participant.primary_id
            break
    if isinstance(location, dict):
        event.x = number(location.get("X"))
        event.y = number(location.get("Y"))
        event.z = number(location.get("Z"))
    return event


def _event_fields(
    event: MatchEvent, data: dict[str, object]
) -> tuple[list[tuple[str, object]], object]:
    kind = event.source_event
    actors: list[tuple[str, object]] = []
    location = None
    if kind == "GoalScored":
        actors = [("scorer", data.get("Scorer")), ("assister", data.get("Assister"))]
        location = data.get("ImpactLocation")
        event.position_subject = "ball"
        event.speed = number(data.get("GoalSpeed"))
        event.round_seconds = number(data.get("GoalTime"))
    elif kind == "StatfeedEvent":
        name = data.get("EventName")
        if isinstance(name, str) and name:
            event.kind = f"Stat:{name}"
        actors = [("actor", data.get("MainTarget")), ("target", data.get("SecondaryTarget"))]
    elif kind == "CrossbarHit":
        location = data.get("BallLocation")
        event.position_subject = "ball"
        event.speed = number(data.get("BallSpeed"))
    elif kind == "BallHit":
        players = data.get("Players")
        if isinstance(players, list):
            actors = [("hitter", player) for player in players]
        ball = data.get("Ball")
        if isinstance(ball, dict):
            location = ball.get("Location")
            event.speed = number(ball.get("PostHitSpeed"))
            _measurements(event, ball, ("PreHitSpeed", "PostHitSpeed"))
        event.position_subject = "ball"
    elif kind == "BoostPickup":
        actors = [("collector", data.get("Player"))]
        location = data.get("Location")
        event.position_subject = "boost_pickup"
    elif kind in ("PlayerJoined", "PlayerLeft"):
        actors = [("player", data)]
    else:
        # Preserve recognizable coordinates on future discrete event types too.
        for key in ("Location", "ImpactLocation", "BallLocation"):
            if isinstance(data.get(key), dict):
                location = data[key]
                if key in ("ImpactLocation", "BallLocation"):
                    event.position_subject = "ball"
                break
    last_touch = data.get("BallLastTouch")
    if isinstance(last_touch, dict):
        actors.append(("last_touch", last_touch.get("Player")))
        speed = number(last_touch.get("Speed"))
        if speed is not None:
            event.details["LastTouchSpeed"] = speed
    _measurements(event, data, ("ImpactForce", "BoostAmount"))
    winner = integer(data.get("WinnerTeamNum"))
    if winner in (0, 1):
        event.details["WinnerTeamNum"] = winner
    for key in ("EventName", "Type", "BoostType", "FileName", "Date"):
        value = data.get(key)
        if isinstance(value, str):
            event.details[key] = value
    return actors, location


def _measurements(event: MatchEvent, data: dict[str, object], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = number(data.get(key))
        if value is not None:
            event.details[key] = value
