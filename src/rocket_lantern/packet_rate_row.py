"""Per-installation rate comparison and explicit configuration actions."""

import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.packet_configuration import ConfigurationProblem, RateConfiguration
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

LOGGER = logging.getLogger(__name__)


class PacketRateRow(QWidget):
    apply_requested = Signal(object)

    def __init__(self, configuration: RateConfiguration, target: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.configuration = configuration
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.directory = QLabel(
            f"{configuration.installation.launcher} · {configuration.installation.config_directory}"
        )
        self.directory.setWordWrap(True)
        self.directory.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.directory)
        self.file = QLabel()
        self.file.setWordWrap(True)
        layout.addWidget(self.file)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.open_button = QPushButton(T("Ouvrir le dossier"))
        self.open_button.clicked.connect(self._open_directory)
        buttons.addWidget(self.open_button)
        self.apply_button = QPushButton()
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self._request_apply)
        buttons.addWidget(self.apply_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.set_target(target)

    def _request_apply(self) -> None:
        self.apply_requested.emit(self.configuration)

    def set_target(self, target: int, busy: bool = False) -> None:
        configuration = self.configuration
        self.apply_button.setText(T("Appliquer {rate}", rate=target))
        self.apply_button.setEnabled(
            not busy and configuration.can_apply and configuration.rate != target
        )
        if configuration.document is None:
            self.file.clear()
        else:
            self.file.setText(
                T("Fichier à configurer : {name}", name=configuration.document.path.name)
            )
            if configuration.inherited is not None:
                self.file.setText(
                    T(
                        "Fichier : {name} · valeur héritée de {source}",
                        name=configuration.document.path.name,
                        source=configuration.inherited.path.name,
                    )
                )
        self._show_comparison(target)

    def _show_comparison(self, target: int) -> None:
        configuration = self.configuration
        color = "#c87518"
        if configuration.problem == ConfigurationProblem.MISSING:
            message = T("Aucun fichier Stats API trouvé dans ce dossier.")
        elif configuration.problem == ConfigurationProblem.UNREADABLE:
            message = T("Impossible de lire la configuration. Vérifiez les droits du fichier.")
        elif configuration.problem == ConfigurationProblem.AMBIGUOUS:
            message = T(
                "Configuration ambiguë : sections ou paramètres dupliqués. Corrigez le fichier."
            )
        elif configuration.problem == ConfigurationProblem.INVALID:
            message = T("Valeur PacketSendRate invalide ; le réglage souhaité peut la remplacer.")
        elif configuration.rate == 0:
            message = T("PacketSendRate = 0 : l’API est désactivée.")
        elif configuration.rate is not None and configuration.rate < target:
            message = T(
                "{rate} paquets/s : inférieur au réglage ; l’affichage peut être retardé.",
                rate=format(configuration.rate, ".12g"),
            )
        elif configuration.rate == target:
            color = "#23834a"
            message = T("PacketSendRate conforme : {rate} paquets/s.", rate=target)
        else:
            color = "#408fc4"
            message = T(
                "{rate} paquets/s : supérieur au réglage, cadence suffisante.",
                rate=format(configuration.rate, ".12g"),
            )
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(message)

    def _open_directory(self) -> None:
        directory = self.configuration.installation.config_directory
        try:
            opened = directory.is_dir() and QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(directory))
            )
        except OSError as error:
            LOGGER.warning("Cannot open game configuration directory %s: %s", directory, error)
            opened = False
        if not opened:
            self.status.setText(T("Impossible d’ouvrir le dossier. Relancez la détection."))
