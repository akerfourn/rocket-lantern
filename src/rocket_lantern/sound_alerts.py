"""Persistent sound rules and localized trigger/subject choices, without audio I/O."""

import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

from rocket_lantern.boost_overlay_mode import PRIVATE_PLAYLISTS
from rocket_lantern.i18n import text as T

MAX_RULES = 128
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"})


class SoundAlertMode(StrEnum):
    NEVER = "never"
    PRIVATE = "private"
    ALL = "all"

    def allows(self, playlist: int | None) -> bool:
        if self == SoundAlertMode.ALL:
            return True
        return (
            self == SoundAlertMode.PRIVATE
            and type(playlist) is int
            and playlist in PRIVATE_PLAYLISTS
        )


class SoundTrigger(StrEnum):
    ASSIST = "assist"
    GOAL = "goal"
    SAVE = "save"
    EPIC_SAVE = "epic_save"
    DEMOLISH = "demolish"
    DEMOLISHED = "demolished"


class PlayerScope(StrEnum):
    SELF = "self"
    TEAMMATES = "teammates"
    TEAM = "team"
    OPPONENTS = "opponents"
    EVERYONE = "everyone"


class SoundKind(StrEnum):
    WINDOWS = "windows"
    FILE = "file"


TRIGGER_LABELS = {
    SoundTrigger.ASSIST: T("Passe décisive"),
    SoundTrigger.GOAL: T("But marqué"),
    SoundTrigger.SAVE: T("Arrêt"),
    SoundTrigger.EPIC_SAVE: T("Arrêt miraculeux"),
    SoundTrigger.DEMOLISH: T("Démolition effectuée"),
    SoundTrigger.DEMOLISHED: T("Démolition subie"),
}
SUBJECT_LABELS = {
    SoundTrigger.ASSIST: T("Passeur :"),
    SoundTrigger.GOAL: T("Buteur :"),
    SoundTrigger.SAVE: T("Joueur qui réalise l’arrêt :"),
    SoundTrigger.EPIC_SAVE: T("Joueur qui réalise l’arrêt :"),
    SoundTrigger.DEMOLISH: T("Joueur qui démolit :"),
    SoundTrigger.DEMOLISHED: T("Joueur démoli :"),
}
SCOPE_LABELS = {
    PlayerScope.SELF: T("Moi"),
    PlayerScope.TEAMMATES: T("Mes coéquipiers (sans moi)"),
    PlayerScope.TEAM: T("Mon équipe (moi inclus)"),
    PlayerScope.OPPONENTS: T("Les adversaires"),
    PlayerScope.EVERYONE: T("Tout le monde"),
}
WINDOWS_SOUNDS = {
    "SystemAsterisk": T("Windows · Information"),
    "SystemExclamation": T("Windows · Exclamation"),
    "SystemHand": T("Windows · Erreur"),
    "Notification.Default": T("Windows · Notification"),
    "Notification.Mail": T("Windows · Courrier"),
    "Notification.Reminder": T("Windows · Rappel"),
}


@dataclass(frozen=True)
class SoundRef:
    kind: SoundKind = SoundKind.WINDOWS
    value: str = "SystemAsterisk"
    name: str = ""


@dataclass(frozen=True)
class SoundRule:
    id: str
    trigger: SoundTrigger
    scope: PlayerScope
    sound: SoundRef = SoundRef()
    enabled: bool = True


@dataclass(frozen=True)
class SoundAlertConfig:
    mode: SoundAlertMode = SoundAlertMode.NEVER
    volume: int = 70
    rules: tuple[SoundRule, ...] = ()

    def serialize(self) -> str:
        return json.dumps({"version": 1, **asdict(self)}, ensure_ascii=False)


def parse_sound_config(value: str) -> SoundAlertConfig:
    if len(value) > 256 * 1024:
        raise ValueError("Sound alert configuration is too large")
    data = json.loads(value)
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("Unsupported sound alert configuration")
    volume = data.get("volume")
    if type(volume) is not int or not 0 <= volume <= 100:
        raise ValueError("Invalid sound alert volume")
    rules = data.get("rules")
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValueError("Invalid sound alert rule list")
    parsed = tuple(_parse_rule(rule) for rule in rules)
    if len({rule.id for rule in parsed}) != len(parsed):
        raise ValueError("Duplicate sound alert rule IDs")
    return SoundAlertConfig(SoundAlertMode(data.get("mode")), volume, parsed)


def _parse_rule(value: object) -> SoundRule:
    if not isinstance(value, dict):
        raise ValueError("Invalid sound alert rule")
    identifier = value.get("id")
    if not isinstance(identifier, str):
        raise ValueError("Missing sound alert rule ID")
    UUID(identifier)
    enabled = value.get("enabled")
    if type(enabled) is not bool:
        raise ValueError("Invalid sound alert activation")
    sound = value.get("sound")
    if not isinstance(sound, dict):
        raise ValueError("Invalid sound reference")
    kind = SoundKind(sound.get("kind"))
    reference = sound.get("value")
    name = sound.get("name", "")
    if not isinstance(reference, str) or not isinstance(name, str) or len(name) > 255:
        raise ValueError("Invalid sound reference")
    if kind == SoundKind.WINDOWS and reference not in WINDOWS_SOUNDS:
        raise ValueError("Unknown Windows sound")
    if (
        kind == SoundKind.FILE
        and re.fullmatch(r"[0-9a-f]{64}\.(mp3|wav|ogg|flac|m4a|aac|opus|wma)", reference) is None
    ):
        raise ValueError("Invalid imported sound filename")
    return SoundRule(
        identifier,
        SoundTrigger(value.get("trigger")),
        PlayerScope(value.get("scope")),
        SoundRef(kind, reference, name),
        enabled,
    )
