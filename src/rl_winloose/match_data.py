"""Typed, compact match observations independent of Qt and SQLite."""

import hashlib
import json
import math
from dataclasses import asdict, astuple, dataclass, field


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
class PlayerStats:
    """Latest known cumulative counters for a participant."""

    primary_id: str
    name: str
    team: int
    score: int | None = None
    goals: int | None = None
    shots: int | None = None
    assists: int | None = None
    saves: int | None = None
    touches: int | None = None
    car_touches: int | None = None
    demos: int | None = None


@dataclass
class MatchEvent:
    """Selected event fields; actor links are optional and never guessed by name."""

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


@dataclass
class MatchSnapshot:
    """Last observations and important events, without periodic telemetry history."""

    guid: str
    observed_at: str
    playlist: int | None = None
    arena: str | None = None
    blue_score: int | None = None
    orange_score: int | None = None
    overtime: bool | None = None
    time_seconds: int | None = None
    winner: int | None = None
    final_observed: bool = False
    replay_active: bool = False
    players: dict[str, PlayerStats] = field(default_factory=dict)
    shortcuts: dict[tuple[int, int], str] = field(default_factory=dict)
    events: dict[str, MatchEvent] = field(default_factory=dict)

    def signature(self) -> tuple[object, ...]:
        """Detect meaningful summary changes without writing on every periodic tick."""
        return (
            self.playlist,
            self.arena,
            self.blue_score,
            self.orange_score,
            self.overtime,
            self.winner,
            self.final_observed,
            tuple(astuple(player) for player in self.players.values()),
            tuple(self.events),
        )

    def update(self, data: dict[str, object], observed_at: str) -> None:
        """Merge a state while retaining departed players and omitted fields."""
        self.observed_at = observed_at
        game = data.get("Game")
        if not isinstance(game, dict):
            return
        self.replay_active = game.get("bReplay") is True
        if self.replay_active:
            return
        if type(game.get("PlaylistId")) is int:
            self.playlist = game["PlaylistId"]
        if isinstance(game.get("Arena"), str):
            self.arena = game["Arena"]
        if type(game.get("bOvertime")) is bool:
            self.overtime = game["bOvertime"]
        time_seconds = integer(game.get("TimeSeconds"))
        if time_seconds is not None:
            self.time_seconds = time_seconds
        teams = game.get("Teams", [])
        if isinstance(teams, list):
            for team in teams:
                if not isinstance(team, dict):
                    continue
                score = integer(team.get("Score"))
                if score is None:
                    continue
                if team.get("TeamNum") == 0:
                    self.blue_score = score
                elif team.get("TeamNum") == 1:
                    self.orange_score = score
                if game.get("bHasWinner") is True and team.get("Name") == game.get("Winner"):
                    winner = integer(team.get("TeamNum"))
                    if winner in (0, 1):
                        self.winner = winner
        self._update_players(data.get("Players"))
        if game.get("bHasWinner") is True or self.winner is not None:
            self.final_observed = True

    def _update_players(self, value: object) -> None:
        if not isinstance(value, list):
            return
        self.shortcuts.clear()
        ambiguous_shortcuts: set[tuple[int, int]] = set()
        counters = {
            "Score": "score",
            "Goals": "goals",
            "Shots": "shots",
            "Assists": "assists",
            "Saves": "saves",
            "Touches": "touches",
            "CarTouches": "car_touches",
            "Demos": "demos",
        }
        for item in value:
            if not isinstance(item, dict):
                continue
            primary_id = item.get("PrimaryId")
            name = item.get("Name")
            team = item.get("TeamNum")
            if not isinstance(primary_id, str) or primary_id == "":
                continue
            if not isinstance(name, str) or type(team) is not int or team not in (0, 1):
                continue
            player = self.players.get(primary_id)
            if player is None:
                player = PlayerStats(primary_id, name, team)
                self.players[primary_id] = player
            player.name = name
            player.team = team
            for api_name, attribute in counters.items():
                counter = integer(item.get(api_name))
                if counter is not None:
                    setattr(player, attribute, counter)
            shortcut = integer(item.get("Shortcut"))
            if shortcut is not None:
                key = (team, shortcut)
                if key in self.shortcuts:
                    ambiguous_shortcuts.add(key)
                self.shortcuts[key] = primary_id
        for key in ambiguous_shortcuts:
            del self.shortcuts[key]

    def _participant(self, value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        primary_id = value.get("PrimaryId")
        if isinstance(primary_id, str) and primary_id in self.players:
            return primary_id
        team = integer(value.get("TeamNum"))
        shortcut = integer(value.get("Shortcut"))
        if team is None or shortcut is None:
            return None
        primary_id = self.shortcuts.get((team, shortcut))
        if primary_id is None:
            return None
        if value.get("Name") != self.players[primary_id].name:
            return None
        return primary_id

    def add_event(self, kind: str, data: dict[str, object], observed_at: str) -> None:
        """Keep goals, stat awards and crossbar hits with stable duplicate protection."""
        actor = data.get("Scorer")
        secondary = data.get("Assister")
        location = data.get("ImpactLocation")
        event_name = kind
        speed = number(data.get("GoalSpeed"))
        if kind == "StatfeedEvent":
            name = data.get("EventName")
            if not isinstance(name, str) or name == "":
                return
            event_name = f"Stat:{name}"
            actor = data.get("MainTarget")
            secondary = data.get("SecondaryTarget")
        elif kind == "CrossbarHit":
            last_touch = data.get("BallLastTouch")
            actor = None
            if isinstance(last_touch, dict):
                actor = last_touch.get("Player")
            location = data.get("BallLocation")
            speed = number(data.get("BallSpeed"))
        team = None
        if isinstance(actor, dict):
            team = integer(actor.get("TeamNum"))
        event = MatchEvent(
            event_name,
            observed_at,
            self.time_seconds,
            self.overtime,
            self._participant(actor),
            self._participant(secondary),
            team,
            speed,
            number(data.get("GoalTime")),
        )
        if isinstance(location, dict):
            event.x = number(location.get("X"))
            event.y = number(location.get("Y"))
            event.z = number(location.get("Z"))
        identity = asdict(event)
        identity.pop("observed_at")
        identity.pop("fingerprint")
        # Unresolved actors must not collapse distinct events from different players.
        identity["actor_hint"] = actor
        identity["secondary_hint"] = secondary
        encoded = json.dumps(identity, sort_keys=True, ensure_ascii=True).encode()
        event.fingerprint = hashlib.sha256(encoded).hexdigest()
        self.events.setdefault(event.fingerprint, event)


class MatchCollector:
    """Retain at most two match summaries to flush a match when the next one arrives."""

    def __init__(self) -> None:
        self.snapshots: dict[str, MatchSnapshot] = {}

    def observe(self, message: dict[str, object], observed_at: str) -> MatchSnapshot | None:
        """Extract only explicitly supported summary and important event fields."""
        data = message.get("Data")
        if not isinstance(data, dict):
            return None
        guid = data.get("MatchGuid")
        if not isinstance(guid, str) or guid == "":
            return None
        snapshot = self.snapshots.get(guid)
        if snapshot is None:
            snapshot = MatchSnapshot(guid, observed_at)
            self.snapshots[guid] = snapshot
            if len(self.snapshots) > 2:
                del self.snapshots[next(iter(self.snapshots))]
        event = message.get("Event")
        if event == "UpdateState":
            snapshot.update(data, observed_at)
        elif event == "ClockUpdatedSeconds":
            time_seconds = integer(data.get("TimeSeconds"))
            if time_seconds is not None:
                snapshot.time_seconds = time_seconds
            if type(data.get("bOvertime")) is bool:
                snapshot.overtime = data["bOvertime"]
        elif event == "MatchEnded":
            winner = integer(data.get("WinnerTeamNum"))
            if winner in (0, 1):
                snapshot.winner = winner
        elif event in ("GoalScored", "StatfeedEvent", "CrossbarHit"):
            if not snapshot.replay_active and data.get("bReplay") is not True:
                snapshot.add_event(event, data, observed_at)
        return snapshot
