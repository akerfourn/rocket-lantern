"""Optional first-run guide using the existing, explicit game configuration actions."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from rocket_lantern.game_installations_panel import GameInstallationsPanel
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class OnboardingDialog(QDialog):
    """Explain setup without automatic discovery, INI writes or mandatory steps."""

    def __init__(self, port: int, language: str, rate: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.outcome = "skipped"
        self.setWindowTitle(T("Bienvenue dans RocketLantern"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(680, min(560, max(300, self.screen().availableGeometry().height() - 80)))
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = QLabel(T("Préparons votre première partie"))
        heading.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(heading)
        introduction = QLabel(
            T(
                "RocketLantern reçoit les données de la Stats API de Rocket League. "
                "Activez-la pour afficher vos matchs et le boost de vos coéquipiers."
            )
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        form = QFormLayout()
        self.language = QComboBox()
        self.language.addItem("Français", "fr")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(language))
        form.addRow(QLabel(T("Langue :")), self.language)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(port)
        form.addRow(QLabel(T("Port local :")), self.port)
        layout.addLayout(form)
        instructions = QLabel(
            T(
                "1. Fermez Rocket League, puis vérifiez les configurations ci-dessous.\n"
                "2. Appliquez le débit souhaité aux installations à configurer "
                "(10 paquets/s recommandés). Chaque modification crée une sauvegarde.\n"
                "3. Relancez Rocket League et jouez un match. Votre compte est détecté "
                "automatiquement ; sinon, sélectionnez votre joueur dans RocketLantern."
            )
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.installations = GameInstallationsPanel(content)
        self.installations.set_packet_rate(rate)
        layout.addWidget(self.installations)
        hint = QLabel(
            T(
                "Le port doit correspondre au WebPort de la Stats API. "
                "Vous pourrez retrouver cet assistant dans les paramètres, "
                "même si vous passez cette étape."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll.setWidget(content)
        root.addWidget(scroll)
        buttons = QHBoxLayout()
        self.skip_button = QPushButton(T("Passer pour le moment"))
        self.skip_button.clicked.connect(self.reject)
        buttons.addWidget(self.skip_button)
        buttons.addStretch()
        self.finish_button = QPushButton(T("Terminer"))
        self.finish_button.clicked.connect(self._finish)
        buttons.addWidget(self.finish_button)
        root.addLayout(buttons)
        self.installations.busy_changed.connect(self._busy_changed)
        self.installations.configurations_changed.connect(self._fit_results)

    def _fit_results(self) -> None:
        if self.installations.rows:
            available_height = max(300, self.screen().availableGeometry().height() - 80)
            self.resize(self.width(), min(760, available_height))

    def _busy_changed(self, busy: bool) -> None:
        self.skip_button.setEnabled(not busy)
        self.finish_button.setEnabled(not busy)

    def _finish(self) -> None:
        if not self.installations.is_busy:
            self.outcome = "completed"
            self.accept()

    def reject(self) -> None:
        """Let a requested check or update finish before destroying its controls."""
        if not self.installations.is_busy:
            super().reject()
