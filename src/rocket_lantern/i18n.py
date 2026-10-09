"""Qt translation catalogs and deferred texts that retain their formatting values."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from string import Formatter

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, QObject, QTranslator, Signal
from PySide6.QtWidgets import QApplication

TRANSLATION_DIRECTORY = Path(__file__).parent / "assets" / "translations"


class LocalizedFormatter(Formatter):
    """Use Qt's decimal separator without changing the underlying numeric values."""

    def format_field(self, value: object, format_spec: str) -> str:
        if isinstance(value, float) and re.fullmatch(r"\.\d+f", format_spec):
            return QLocale().toString(value, "f", int(format_spec[1:-1]))
        return super().format_field(value, format_spec)


@dataclass(frozen=True)
class Text:
    """Keep source text separate from player names, numbers and other supplied values."""

    source: str
    values: dict[str, object] = field(default_factory=dict)
    count: int = -1

    def render(self) -> str:
        translated = QCoreApplication.translate("RocketLantern", self.source, None, self.count)
        values = {}
        for name, value in self.values.items():
            if isinstance(value, (Text, DateText)):
                value = value.render()
            values[name] = value
        return LocalizedFormatter().vformat(translated, (), values)

    def __str__(self) -> str:
        return self.render()


@dataclass(frozen=True)
class DateText:
    """Render an observation in local time and the selected language's date order."""

    value: datetime
    seconds: bool = False

    def render(self) -> str:
        pattern = QLocale().dateFormat(QLocale.FormatType.ShortFormat)
        pattern = re.sub(r"(?<!y)yy(?!y)", "yyyy", pattern)
        pattern += " HH:mm"
        if self.seconds:
            pattern += ":ss"
        return QLocale().toString(QDateTime(self.value.astimezone()), pattern)

    def __str__(self) -> str:
        return self.render()


type DisplayText = str | Text | DateText


def text(source: str, **values: object) -> Text:
    """Mark an application-owned template for translation, never its supplied data."""
    return Text(source, values)


def render(value: DisplayText) -> str:
    if isinstance(value, (Text, DateText)):
        return value.render()
    return value


def system_language() -> str:
    if QLocale.system().language() == QLocale.Language.French:
        return "fr"
    return "en"


class LanguageManager(QObject):
    """Own the installed catalog and broadcast Qt LanguageChange without restarting."""

    changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.setObjectName("languageManager")
        self.language = ""
        self._app = app
        self._translator: QTranslator | None = None
        self.set_language("fr")

    def set_language(self, language: str) -> None:
        if language not in ("fr", "en"):
            raise ValueError(f"Unsupported language: {language}")
        if language == self.language:
            return
        translator = QTranslator(self)
        path = TRANSLATION_DIRECTORY / f"rocket_lantern_{language}.qm"
        if not translator.load(str(path)):
            raise OSError(f"Cannot load translation catalog: {path}")
        if self._translator is not None:
            self._app.removeTranslator(self._translator)
            self._translator.deleteLater()
        self._translator = translator
        locale = QLocale("fr_FR" if language == "fr" else "en_US")
        locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
        QLocale.setDefault(locale)
        self.language = language
        self._app.installTranslator(translator)
        self.changed.emit(language)


def language_manager() -> LanguageManager:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise RuntimeError("A QApplication is required before choosing the language")
    manager = app.findChild(LanguageManager, "languageManager")
    if manager is None:
        manager = LanguageManager(app)
    return manager
