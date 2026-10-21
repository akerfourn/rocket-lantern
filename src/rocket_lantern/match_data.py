"""Typed, compact match observations independent of Qt and SQLite."""

import hashlib
import json
from dataclasses import asdict, astuple, dataclass, field

from rocket_lantern.event_data import MatchEvent, extract_event, integer
from rocket_lantern.event_data import number as number
from rocket_lantern.player_state import PlayerStateTracker


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
    event_revision: int = 0
    states: PlayerStateTracker = field(default_factory=PlayerStateTracker)
    _seen_goals: set[str] = field(default_factory=set)
    states_active: bool = True

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
            self.event_revision,
        )

    def update(
        self, data: dict[str, object], observed_at: str, *, collect_states: bool = False
    ) -> None:
        """Merge a state while retaining departed players and omitted fields."""
        self.observed_at = observed_at
        game = data.get("Game")
        if not isinstance(game, dict):
            return
        if type(game.get("bReplay")) is bool:
            self.replay_active = game["bReplay"]
        if self.replay_active:
            self.interrupt_states(observed_at)
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
        if game.get("bHasWinner") is True:
            self.interrupt_states(observed_at)
            self.states_active = False
        if collect_states and self.states_active:
            for event in self.states.observe(
                data.get("Players"), observed_at, self.time_seconds, self.overtime
            ):
                self._append_event(event)
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
        if isinstance(primary_id, str) and primary_id:
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
        """Keep discrete API events, never an unfiltered payload."""
        event = extract_event(
            kind, data, observed_at, self.time_seconds, self.overtime, self._participant
        )
        self._append_event(event, deduplicate=kind == "GoalScored")

    def interrupt_states(self, observed_at: str) -> None:
        """Mark the end of observable player states without assuming an outcome."""
        for event in self.states.interrupt(observed_at, self.time_seconds, self.overtime):
            self._append_event(event)

    def _append_event(self, event: MatchEvent, *, deduplicate: bool = False) -> None:
        identity = asdict(event)
        identity.pop("fingerprint")
        if deduplicate:
            identity.pop("observed_at")
        else:
            # Identical touches within one clock second are separate occurrences.
            identity["sequence"] = self.event_revision
        encoded = json.dumps(identity, sort_keys=True, ensure_ascii=True).encode()
        event.fingerprint = hashlib.sha256(encoded).hexdigest()
        if deduplicate:
            if event.fingerprint in self._seen_goals:
                return
            self._seen_goals.add(event.fingerprint)
        self.events[event.fingerprint] = event
        self.event_revision += 1


class MatchCollector:
    """Retain two recent summaries plus any older events still awaiting storage."""

    def __init__(self) -> None:
        self.snapshots: dict[str, MatchSnapshot] = {}

    def observe(self, message: dict[str, object], observed_at: str) -> MatchSnapshot | None:
        """Collect discrete events and state transitions, not periodic snapshots."""
        data = message.get("Data")
        if not isinstance(data, dict):
            return None
        guid = data.get("MatchGuid")
        if not isinstance(guid, str) or guid == "":
            return None
        event = message.get("Event")
        if not isinstance(event, str) or not event or event == "ReplayCreated":
            return None
        snapshot = self.snapshots.get(guid)
        if snapshot is None:
            for previous in self.snapshots.values():
                previous.interrupt_states(observed_at)
            snapshot = MatchSnapshot(guid, observed_at)
            self.snapshots[guid] = snapshot
            self.prune()
        snapshot.observed_at = observed_at
        if event == "UpdateState":
            snapshot.update(data, observed_at, collect_states=True)
            return snapshot
        if event == "GoalReplayStart":
            snapshot.interrupt_states(observed_at)
            snapshot.replay_active = True
        elif event == "GoalReplayEnd":
            snapshot.replay_active = False
        elif event == "ClockUpdatedSeconds" and not snapshot.replay_active:
            time_seconds = integer(data.get("TimeSeconds"))
            if time_seconds is not None:
                snapshot.time_seconds = time_seconds
            if type(data.get("bOvertime")) is bool:
                snapshot.overtime = data["bOvertime"]
        elif event == "MatchEnded" and not snapshot.replay_active:
            winner = integer(data.get("WinnerTeamNum"))
            if winner in (0, 1):
                snapshot.winner = winner
        replay_boundary = event in ("GoalReplayStart", "GoalReplayWillEnd", "GoalReplayEnd")
        if replay_boundary or (data.get("bReplay") is not True and not snapshot.replay_active):
            snapshot.add_event(event, data, observed_at)
        if event == "PlayerLeft" and not snapshot.replay_active:
            primary_id = snapshot._participant(data)
            if primary_id is not None:
                for change in snapshot.states.depart(
                    primary_id, observed_at, snapshot.time_seconds, snapshot.overtime
                ):
                    snapshot._append_event(change)
                snapshot.shortcuts = {
                    key: value for key, value in snapshot.shortcuts.items() if value != primary_id
                }
        if event in ("MatchDestroyed", "MatchEnded", "MatchPaused"):
            snapshot.interrupt_states(observed_at)
            snapshot.states_active = False
        elif event in ("RoundStarted", "MatchUnpaused"):
            snapshot.states_active = True
        return snapshot

    def interrupt(self, observed_at: str) -> None:
        """Close coverage intervals on a lost connection, retaining pending events."""
        for snapshot in self.snapshots.values():
            snapshot.interrupt_states(observed_at)

    def prune(self) -> None:
        """Never discard uncommitted events when the database is temporarily unavailable."""
        for guid in list(self.snapshots)[:-2]:
            if not self.snapshots[guid].events:
                del self.snapshots[guid]
