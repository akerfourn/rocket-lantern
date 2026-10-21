"""Turn available player flags into transitions rather than periodic telemetry."""

from rocket_lantern.event_data import EventParticipant, MatchEvent, integer

STATE_FIELDS = (
    "bHasCar",
    "bOnGround",
    "bOnWall",
    "bBoosting",
    "bPowersliding",
    "bDemolished",
    "bSupersonic",
)


class PlayerStateTracker:
    """Retain only the last flags, with explicit gaps in observation coverage."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, bool]] = {}
        self.players: dict[str, EventParticipant] = {}

    def observe(
        self, value: object, observed_at: str, time_seconds: int | None, overtime: bool | None
    ) -> list[MatchEvent]:
        if not isinstance(value, list):
            return self.interrupt(observed_at, time_seconds, overtime)
        current: dict[str, dict[str, bool]] = {}
        for player in value:
            if not isinstance(player, dict):
                continue
            primary_id = player.get("PrimaryId")
            if not isinstance(primary_id, str) or not primary_id:
                continue
            name = player.get("Name")
            if not isinstance(name, str):
                name = None
            self.players[primary_id] = EventParticipant(
                "player",
                primary_id,
                name,
                integer(player.get("TeamNum")),
                integer(player.get("Shortcut")),
            )
            current[primary_id] = {
                key: player[key] for key in STATE_FIELDS if type(player.get(key)) is bool
            }
        return self._transitions(current, observed_at, time_seconds, overtime)

    def interrupt(
        self, observed_at: str, time_seconds: int | None, overtime: bool | None
    ) -> list[MatchEvent]:
        """End known intervals on disconnection, departure or replay playback."""
        return self._transitions({}, observed_at, time_seconds, overtime)

    def depart(
        self, primary_id: str, observed_at: str, time_seconds: int | None, overtime: bool | None
    ) -> list[MatchEvent]:
        """Close the departing player's intervals without interrupting teammates."""
        current = {key: values for key, values in self.values.items() if key != primary_id}
        return self._transitions(current, observed_at, time_seconds, overtime)

    def _transitions(
        self,
        current: dict[str, dict[str, bool]],
        observed_at: str,
        time_seconds: int | None,
        overtime: bool | None,
    ) -> list[MatchEvent]:
        events = []
        for primary_id in dict.fromkeys((*self.values, *current)):
            previous = self.values.get(primary_id, {})
            values = current.get(primary_id, {})
            for key in STATE_FIELDS:
                before = previous.get(key)
                after = values.get(key)
                if before == after:
                    continue
                participant = self.players[primary_id]
                events.append(
                    MatchEvent(
                        f"PlayerState:{key}",
                        observed_at,
                        time_seconds,
                        overtime,
                        actor=primary_id,
                        team=participant.team,
                        source_event="UpdateState",
                        origin="state",
                        details={"previous": before, "value": after},
                        participants=[participant],
                    )
                )
        self.values = current
        self.players = {primary_id: self.players[primary_id] for primary_id in current}
        return events
