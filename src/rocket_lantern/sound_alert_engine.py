"""Match live event roles to sound rules; never play audio or read settings here."""

from collections import deque
from dataclasses import dataclass

from rocket_lantern.event_data import number
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.sound_alerts import (
    PlayerScope,
    SoundAlertConfig,
    SoundRule,
    SoundTrigger,
)

SAVE_DELAY = 0.12
DUPLICATE_WINDOW = 0.1


@dataclass(frozen=True)
class AlertContext:
    snapshot: MatchSnapshot | None
    player_id: str
    replay: bool = False


@dataclass(frozen=True)
class PendingSave:
    due: float
    rules: tuple[SoundRule, ...]


def matches_scope(scope: PlayerScope, subject: PlayerStats, context: AlertContext) -> bool:
    if scope == PlayerScope.EVERYONE:
        return True
    if context.snapshot is None:
        return False
    local = context.snapshot.players.get(context.player_id)
    if local is None:
        return False
    if scope == PlayerScope.SELF:
        return subject.primary_id == local.primary_id
    if scope == PlayerScope.TEAMMATES:
        return subject.team == local.team and subject.primary_id != local.primary_id
    if scope == PlayerScope.TEAM:
        return subject.team == local.team
    return subject.team != local.team


class SoundAlertEngine:
    def __init__(self, config: SoundAlertConfig) -> None:
        self.config = config
        self._context: tuple[str, str, int | None] | None = None
        self._ended = False
        self._recent: deque[tuple[tuple[object, ...], float]] = deque(maxlen=128)
        self._epic: deque[tuple[tuple[object, ...], float]] = deque(maxlen=32)
        self._pending: dict[tuple[object, ...], PendingSave] = {}

    @property
    def pending(self) -> bool:
        return bool(self._pending)

    def clear(self) -> None:
        self._context = None
        self._ended = False
        self._recent.clear()
        self._epic.clear()
        self._pending.clear()

    def configure(self, config: SoundAlertConfig) -> None:
        self.config = config
        self._recent.clear()
        self._epic.clear()
        self._pending.clear()

    def sync_context(self, context: AlertContext) -> None:
        if context.snapshot is None:
            self.clear()
            return
        local = context.snapshot.players.get(context.player_id)
        team = None
        if local is not None:
            team = local.team
        key = (context.snapshot.guid, context.player_id, team)
        if key != self._context:
            ended = self._ended and self._context is not None and key[0] == self._context[0]
            self.clear()
            self._context = key
            self._ended = ended
        if context.replay or not self.config.mode.allows(context.snapshot.playlist):
            self._pending.clear()

    def observe(
        self, message: dict[str, object], context: AlertContext, now: float
    ) -> tuple[SoundRule, ...]:
        self.sync_context(context)
        snapshot = context.snapshot
        data = message.get("Data")
        if snapshot is None or not isinstance(data, dict):
            return ()
        if data.get("MatchGuid", "") != snapshot.guid:
            return ()
        if message.get("Event") == "MatchEnded":
            self._ended = True
            self._pending.clear()
            return ()
        if self._ended or context.replay or data.get("bReplay") is True:
            return ()
        if not self.config.mode.allows(snapshot.playlist):
            return ()
        requests = []
        for trigger, participant, other in self._subjects(message.get("Event"), data):
            primary_id = snapshot.resolve_participant(participant)
            subject = snapshot.players.get(primary_id)
            if subject is None:
                continue
            other_id = snapshot.resolve_participant(other)
            signature = (
                trigger,
                primary_id,
                other_id,
                snapshot.time_seconds,
                snapshot.overtime,
                subject.goals,
                subject.assists,
                subject.saves,
                subject.demos,
                number(data.get("GoalTime")),
            )
            if self._duplicate(signature, now):
                continue
            requests.extend(self._select(trigger, subject, context, now))
        return tuple(requests)

    @staticmethod
    def _subjects(
        event: object, data: dict[str, object]
    ) -> tuple[tuple[SoundTrigger, object, object], ...]:
        if event == "GoalScored":
            return ((SoundTrigger.GOAL, data.get("Scorer"), data.get("Assister")),)
        if event != "StatfeedEvent" or not isinstance(data.get("EventName"), str):
            return ()
        main = data.get("MainTarget")
        secondary = data.get("SecondaryTarget")
        trigger = {
            "Assist": SoundTrigger.ASSIST,
            "Save": SoundTrigger.SAVE,
            "EpicSave": SoundTrigger.EPIC_SAVE,
            "Demolish": SoundTrigger.DEMOLISH,
        }.get(data.get("EventName"))
        if trigger == SoundTrigger.DEMOLISH:
            return ((trigger, main, secondary), (SoundTrigger.DEMOLISHED, secondary, main))
        if trigger is not None:
            return ((trigger, main, secondary),)
        return ()

    def _duplicate(self, signature: tuple[object, ...], now: float) -> bool:
        while self._recent and now - self._recent[0][1] > DUPLICATE_WINDOW:
            self._recent.popleft()
        if any(
            key == signature and 0 <= now - when <= DUPLICATE_WINDOW for key, when in self._recent
        ):
            return True
        self._recent.append((signature, now))
        return False

    def _matching(
        self, trigger: SoundTrigger, subject: PlayerStats, context: AlertContext
    ) -> tuple[SoundRule, ...]:
        return tuple(
            rule
            for rule in self.config.rules
            if rule.enabled
            and rule.trigger == trigger
            and matches_scope(rule.scope, subject, context)
        )

    def _select(
        self, trigger: SoundTrigger, subject: PlayerStats, context: AlertContext, now: float
    ) -> tuple[SoundRule, ...]:
        key = (subject.primary_id, context.snapshot.time_seconds, context.snapshot.overtime)
        matches = self._matching(trigger, subject, context)
        if trigger == SoundTrigger.EPIC_SAVE:
            self._pending.pop(key, None)
            self._epic.append((key, now))
            if not matches:
                matches = self._matching(SoundTrigger.SAVE, subject, context)
        elif trigger == SoundTrigger.SAVE:
            if any(
                previous == key and 0 <= now - when <= SAVE_DELAY for previous, when in self._epic
            ):
                return ()
            if matches:
                if len(self._pending) >= 128 and key not in self._pending:
                    self._pending.pop(next(iter(self._pending)))
                self._pending[key] = PendingSave(now + SAVE_DELAY, matches)
            return ()
        return matches

    def flush(self, context: AlertContext, now: float) -> tuple[SoundRule, ...]:
        self.sync_context(context)
        if context.replay or self._ended:
            self._pending.clear()
        requests = []
        for key, pending in list(self._pending.items()):
            if now >= pending.due:
                requests.extend(pending.rules)
                del self._pending[key]
        return tuple(requests)
