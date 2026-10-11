"""Manual discovery, configuration checks and per-installation rate updates."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from rocket_lantern.game_installations import (
    DiscoveryReport,
    GameInstallation,
    detect_installations,
)
from rocket_lantern.i18n import text as T
from rocket_lantern.packet_configuration import (
    ConfigurationChangedError,
    RateConfiguration,
    apply_packet_rate,
    read_configuration,
)
from rocket_lantern.packet_rate_row import PacketRateRow
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigurationCheck:
    discovery: DiscoveryReport
    configurations: tuple[RateConfiguration, ...]


class TaskSignals(QObject):
    completed = Signal(object)
    failed = Signal(bool)


class DiscoveryTask(QRunnable):
    """Keep launcher and INI reads away from the Qt UI thread."""

    def __init__(
        self,
        detector: Callable[[], DiscoveryReport],
        reader: Callable[[GameInstallation], RateConfiguration] = read_configuration,
    ) -> None:
        super().__init__()
        self.detector = detector
        self.reader = reader
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            report = self.detector()
            configurations = tuple(
                self.reader(installation) for installation in report.installations
            )
        except (OSError, ValueError) as error:
            LOGGER.warning("Game configuration check failed: %s", error)
            self.signals.failed.emit(False)
            return
        self.signals.completed.emit(ConfigurationCheck(report, configurations))


class ApplyTask(QRunnable):
    def __init__(self, configuration: RateConfiguration, rate: int) -> None:
        super().__init__()
        self.configuration = configuration
        self.rate = rate
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            updated, backup = apply_packet_rate(self.configuration, self.rate)
        except (OSError, ValueError) as error:
            LOGGER.warning("Cannot apply PacketSendRate: %s", error)
            self.signals.failed.emit(isinstance(error, ConfigurationChangedError))
            return
        self.signals.completed.emit((updated, backup))


class GameInstallationsPanel(QGroupBox):
    """Read/write only on explicit actions; desired rate changes never edit INIs."""

    configurations_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        detector: Callable[[], DiscoveryReport] = detect_installations,
    ) -> None:
        super().__init__(T("Configuration de Rocket League"), parent)
        self.detector = detector
        self._busy = False
        self.rows: list[PacketRateRow] = []
        layout = QVBoxLayout(self)
        desired = QHBoxLayout()
        desired.addWidget(QLabel(T("Débit souhaité (PacketSendRate) :")))
        self.packet_rate = QSpinBox()
        self.packet_rate.setRange(1, 120)
        self.packet_rate.setValue(10)
        self.packet_rate.valueChanged.connect(self._target_changed)
        desired.addWidget(self.packet_rate)
        desired.addWidget(QLabel(T("paquets/s")))
        desired.addStretch()
        layout.addLayout(desired)
        self.detect_button = QPushButton(T("Vérifier les configurations"))
        self.detect_button.clicked.connect(self._detect)
        layout.addWidget(self.detect_button)
        self.status = QLabel(T("Rechercher les installations Steam et Epic Games à la demande."))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QScrollArea()
        self.results.setWidgetResizable(True)
        self.results.setMaximumHeight(270)
        self.results.hide()
        self.result_widget = QWidget()
        self.result_layout = QVBoxLayout(self.result_widget)
        self.results.setWidget(self.result_widget)
        layout.addWidget(self.results)
        notice = QLabel(
            T("Fermez Rocket League avant d’appliquer. Redémarrez le jeu après modification.")
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

    def _target_changed(self, value: int) -> None:
        for row in self.rows:
            row.set_target(value, self._busy)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.detect_button.setEnabled(not busy)
        self.packet_rate.setEnabled(not busy)
        self._target_changed(self.packet_rate.value())

    def _detect(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.status.setText(T("Recherche des installations en cours…"))
        task = DiscoveryTask(self.detector)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._check_failed)
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _completed(self, check: ConfigurationCheck) -> None:
        self._set_busy(False)
        for row in self.rows:
            self.result_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()
        for configuration in check.configurations:
            row = PacketRateRow(configuration, self.packet_rate.value(), self.result_widget)
            row.apply_requested.connect(self._apply)
            self.result_layout.addWidget(row)
            self.rows.append(row)
        self.results.setVisible(bool(self.rows))
        report = check.discovery
        if not report.supported:
            message = T("La détection des installations est disponible sous Windows uniquement.")
        elif not report.installations:
            message = T("Aucune installation de Rocket League trouvée.")
        else:
            message = T("Installations trouvées : {count}", count=len(report.installations))
        if report.warnings:
            message = T(
                "{result} Certaines sources sont illisibles ; "
                "les résultats peuvent être incomplets.",
                result=message,
            )
        self.status.setText(message)
        self.configurations_changed.emit()

    @Slot(bool)
    def _check_failed(self, changed: bool) -> None:
        self._set_busy(False)
        self.status.setText(T("Impossible de rechercher les installations. Réessayez."))

    @Slot(object)
    def _apply(self, configuration: RateConfiguration) -> None:
        if (
            self._busy
            or not configuration.can_apply
            or configuration.rate == self.packet_rate.value()
        ):
            return
        self._set_busy(True)
        self.status.setText(T("Application du réglage en cours…"))
        task = ApplyTask(configuration, self.packet_rate.value())
        task.signals.completed.connect(self._applied)
        task.signals.failed.connect(self._apply_failed)
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _applied(self, result: tuple[RateConfiguration, Path]) -> None:
        configuration, backup = result
        for row in self.rows:
            if row.configuration.installation == configuration.installation:
                row.configuration = configuration
        self._set_busy(False)
        self.status.setText(
            T("Réglage appliqué. Sauvegarde : {name}. Redémarrez Rocket League.", name=backup.name)
        )

    @Slot(bool)
    def _apply_failed(self, changed: bool) -> None:
        self._set_busy(False)
        if changed:
            self.status.setText(T("Le fichier a changé. Vérifiez à nouveau avant d’appliquer."))
        else:
            self.status.setText(
                T("Impossible d’appliquer le réglage. Vérifiez les droits et fermez le jeu.")
            )
