"""Stable identifiers and configurable definitions for independent match annotations."""

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from rocket_lantern.evaluations import Evaluation, evaluation_label
from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T

DEFAULT_LIST = "smurfing"
SYMBOLS = ("tag", "not_evaluated", "no_suspicion", "possible", "strong")


@dataclass(frozen=True)
class LabelList:
    id: str
    name: str
    enabled: bool = True
    position: int = 0

    @property
    def title(self) -> DisplayText:
        if self.id == DEFAULT_LIST and self.name == "Suspicion de smurf":
            return T("Suspicion de smurf")
        return self.name


@dataclass(frozen=True)
class Label:
    id: str
    list_id: str
    name: str
    color: str = "#aab1ba"
    symbol: str = "tag"
    enabled: bool = True
    position: int = 0
    shortcut: str = ""

    @property
    def title(self) -> DisplayText:
        defaults = {item.id: item.name for item in default_labels()}
        if self.id in defaults and self.name == defaults[self.id]:
            return evaluation_label(Evaluation(self.id))
        return self.name


def custom_id() -> str:
    return f"custom:{uuid4()}"


def validate_custom_id(value: str) -> None:
    if not value.startswith("custom:"):
        raise ValueError("Custom identifiers must start with custom:")
    try:
        UUID(value.removeprefix("custom:"))
    except ValueError as error:
        raise ValueError("A custom UUID is required") from error


def validate_name(value: str) -> None:
    if not value.strip() or len(value) > 80 or any(ord(character) < 32 for character in value):
        raise ValueError("A name of 1 to 80 characters is required")


def validate_color(value: str) -> None:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError("A color in #RRGGBB format is required")


def default_labels() -> tuple[Label, ...]:
    definitions = (
        ("Non évalué", "#aab1ba"),
        ("Aucune suspicion", "#62d694"),
        ("Suspicion possible", "#f4be60"),
        ("Forte suspicion", "#ff7b86"),
    )
    return tuple(
        Label(
            value.value,
            DEFAULT_LIST,
            name,
            color,
            value.value,
            True,
            index,
            f"Ctrl+Shift+F{index + 1}",
        )
        for index, (value, (name, color)) in enumerate(zip(Evaluation, definitions, strict=True))
    )
