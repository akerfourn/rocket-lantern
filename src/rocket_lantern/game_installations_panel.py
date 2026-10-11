"""Manual installation discovery and explicit opening of configuration folders."""

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from rocket_lantern.game_installations import (
    DiscoveryReport,
    GameInstallation,
    detect_installations,
)
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

LOGGER = logging.getLogger(__name__)


class DiscoverySignals(QObject):
    completed = Signal(object)
    failed = Signal()


class DiscoveryTask(QRunnable):
    """Keep disk/registry reads away from the Qt UI thread."""

    def __init__(self, detector: Callable[[], DiscoveryReport]) -> None:
        super().__init__()
        self.detector = detector
        self.signals = DiscoverySignals()

    def run(self) -> None:
        try:
            report = self.detector()
        except (OSError, ValueError) as error:
            LOGGER.warning("Game installation detection failed: %s", error)
            self.signals.failed.emit()
            return
        self.signals.completed.emit(report)


class GameInstallationsPanel(QGroupBox):
    """Keep results only for this application run; rescan solely on request."""

    def __init__(
        self,
        parent: QWidget | None = None,
        detector: Callable[[], DiscoveryReport] = detect_installations,
    ) -> None:
        super().__init__(T("Configuration de Rocket League"), parent)
        self.detector = detector
        self._busy = False
        self.installations: tuple[GameInstallation, ...] = ()
        layout = QVBoxLayout(self)
        self.status = QLabel(T("Rechercher les installations Steam et Epic Games à la demande."))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.detect_button = QPushButton(T("Détecter les installations"))
        self.detect_button.clicked.connect(self._detect)
        actions.addWidget(self.detect_button)
        self.open_button = QPushButton(T("Ouvrir le dossier"))
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_directory)
        actions.addWidget(self.open_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.selector = QComboBox()
        self.selector.setMinimumContentsLength(24)
        self.selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.selector.setVisible(False)
        self.selector.currentIndexChanged.connect(self._selection_changed)
        layout.addWidget(self.selector)
        self.directory = QLabel()
        self.directory.setWordWrap(True)
        self.directory.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.directory)
        self.file = QLabel()
        self.file.setWordWrap(True)
        layout.addWidget(self.file)

    def _detect(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.detect_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.status.setText(T("Recherche des installations en cours…"))
        task = DiscoveryTask(self.detector)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _completed(self, report: DiscoveryReport) -> None:
        self._busy = False
        self.detect_button.setEnabled(True)
        self.installations = report.installations
        self.selector.clear()
        for installation in self.installations:
            self.selector.addItem(f"{installation.launcher} · {installation.directory}")
        self.selector.setVisible(len(self.installations) > 1)
        self._selection_changed(self.selector.currentIndex())
        if not report.supported:
            message = T("La détection des installations est disponible sous Windows uniquement.")
        elif not self.installations:
            message = T("Aucune installation de Rocket League trouvée.")
        else:
            message = T("Installations trouvées : {count}", count=len(self.installations))
        if report.warnings:
            message = T(
                "{result} Certaines sources sont illisibles ; "
                "les résultats peuvent être incomplets.",
                result=message,
            )
        self.status.setText(message)

    @Slot()
    def _failed(self) -> None:
        self._busy = False
        self.detect_button.setEnabled(True)
        self.open_button.setEnabled(bool(self.installations))
        self.status.setText(T("Impossible de rechercher les installations. Réessayez."))

    def _selection_changed(self, index: int) -> None:
        self.open_button.setEnabled(not self._busy and 0 <= index < len(self.installations))
        if index < 0 or index >= len(self.installations):
            self.directory.clear()
            self.file.clear()
            return
        installation = self.installations[index]
        self.directory.setText(str(installation.config_directory))
        if installation.config_file is None:
            self.file.setText(T("Aucun fichier Stats API trouvé dans ce dossier."))
        else:
            self.file.setText(
                T("Fichier à configurer : {name}", name=installation.config_file.name)
            )

    def _open_directory(self) -> None:
        index = self.selector.currentIndex()
        if self._busy or not 0 <= index < len(self.installations):
            return
        directory = self.installations[index].config_directory
        try:
            opened = directory.is_dir() and QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(directory))
            )
        except OSError as error:
            LOGGER.warning("Cannot open game configuration directory %s: %s", directory, error)
            opened = False
        if not opened:
            self.status.setText(T("Impossible d’ouvrir le dossier. Relancez la détection."))
