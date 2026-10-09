"""Latest live observations only; this state never writes to SQLite."""

from dataclasses import dataclass, field

from rocket_lantern.match_data import MatchSnapshot, integer, number

PHASE_EVENTS = {
    "CountdownBegin": "Compte à rebours",
    "RoundStarted": "En cours",
    "MatchPaused": "En pause",
    "MatchUnpaused": "En cours",
    "MatchEnded": "Terminée · dernier état observé",
    "PodiumStart": "Podium · dernier état observé",
}


@dataclass
class LiveMatchState:
    """Replace every periodic snapshot; keep no telemetry or event history."""

    snapshot: MatchSnapshot | None = None
    ball_speed: float | None = None
    last_touch_team: int | None = None
    boost: dict[str, int | None] = field(default_factory=dict)
    omitted_boost: set[str] = field(default_factory=set)
    phase: str = "En attente de données de partie."
    goal_replay: bool = False

    def clear(self, reason: str) -> None:
        """Discard stale values on disconnect, departure or historical playback."""
        self.snapshot = None
        self.ball_speed = None
        self.last_touch_team = None
        self.boost.clear()
        self.omitted_boost.clear()
        self.goal_replay = False
        self.phase = reason

    def observe(self, message: dict[str, object], observed_at: str, history_replay: bool) -> None:
        """Handle normalized observations without guessing unreceived values."""
        event = message.get("Event")
        data = message.get("Data")
        if not isinstance(data, dict):
            return
        if event == "ReplayCreated" or history_replay:
            self.clear("Replay historique · vue en direct désactivée.")
            return
        guid = data.get("MatchGuid")
        if event == "UpdateState":
            self._update(data, observed_at)
            return
        if event == "MatchCreated":
            if self.snapshot is None or guid != self.snapshot.guid:
                self.clear("Nouvelle partie · en attente du premier état.")
            return
        if event == "MatchDestroyed" and self.snapshot is not None and self.snapshot.guid == "":
            self.clear("Partie quittée · en attente d’une nouvelle partie.")
            return
        if self.snapshot is None or guid != self.snapshot.guid:
            return
        if event == "MatchDestroyed":
            self.clear("Partie quittée · en attente d’une nouvelle partie.")
        elif event == "GoalReplayStart":
            self.goal_replay = True
        elif event == "GoalReplayEnd":
            self.goal_replay = False
        elif event == "ClockUpdatedSeconds" and not self.goal_replay:
            self.snapshot.time_seconds = integer(data.get("TimeSeconds"))
            if type(data.get("bOvertime")) is bool:
                self.snapshot.overtime = data["bOvertime"]
        elif isinstance(event, str) and event in PHASE_EVENTS:
            self.phase = PHASE_EVENTS[event]

    def _update(self, data: dict[str, object], observed_at: str) -> None:
        game = data.get("Game")
        if not isinstance(game, dict):
            return
        guid = data.get("MatchGuid")
        if not isinstance(guid, str):
            guid = ""
        if self.snapshot is None or guid != self.snapshot.guid:
            self.clear("En cours")
        self.goal_replay = game.get("bReplay") is True
        if self.goal_replay:
            return
        snapshot = MatchSnapshot(guid, observed_at)
        snapshot.update(data, observed_at)
        self.snapshot = snapshot
        self._update_boost(data.get("Players"))
        ball = game.get("Ball")
        self.ball_speed = None
        self.last_touch_team = None
        if isinstance(ball, dict):
            speed = number(ball.get("Speed"))
            if speed is not None and speed >= 0:
                self.ball_speed = speed
            team = integer(ball.get("TeamNum"))
            if team in (0, 1):
                self.last_touch_team = team
        if snapshot.final_observed:
            self.phase = "Terminée · dernier état observé"

    def _update_boost(self, value: object) -> None:
        """Use received values only; missing fields must not retain an earlier boost."""
        self.boost.clear()
        self.omitted_boost.clear()
        if not isinstance(value, list) or self.snapshot is None:
            return
        for item in value:
            if not isinstance(item, dict):
                continue
            primary_id = item.get("PrimaryId")
            if not isinstance(primary_id, str) or primary_id not in self.snapshot.players:
                continue
            boost = integer(item.get("Boost"))
            if boost is not None and boost > 100:
                boost = None
            if item.get("bHasCar") is False:
                boost = None
            elif "Boost" not in item:
                self.omitted_boost.add(primary_id)
            self.boost[primary_id] = boost
