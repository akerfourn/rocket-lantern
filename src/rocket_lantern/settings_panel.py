"""Application preferences, separated from the match views."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.game_installations_panel import GameInstallationsPanel
from rocket_lantern.hotkey_settings import HotkeySettings
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.updates import RELEASE_URL


class SettingsPanel(QDialog):
    """Expose connection, language and startup preferences."""

    opened = Signal()
    hidden = Signal()

    def __init__(self, port: int, language: str, default_tab: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(T("Paramètres"))
        self.resize(460, 210)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_configuration_results)
        root = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout = self._content_layout
        self._scroll.setWidget(content)
        root.addWidget(self._scroll)
        heading = QHBoxLayout()
        title = QLabel(T("Paramètres"))
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        heading.addWidget(title, 1)
        layout.addLayout(heading)

        fields = QWidget()
        fields.setMaximumWidth(620)
        form = QFormLayout(fields)
        form.setContentsMargins(0, 0, 0, 0)
        connection = QHBoxLayout()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(port)
        connection.addWidget(self.port)
        self.reconnect = QPushButton(T("Reconnecter"))
        connection.addWidget(self.reconnect)
        connection.addStretch()
        form.addRow(QLabel(T("Port local :")), connection)
        self.language = QComboBox()
        self.language.setObjectName("languageSelector")
        self.language.addItem("Français", "fr")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(language))
        form.addRow(QLabel(T("Langue :")), self.language)
        self.default_tab = QComboBox()
        self.default_tab.addItem(T("Matchs"), "matches")
        self.default_tab.addItem(T("Partie en cours"), "live")
        index = self.default_tab.findData(default_tab)
        self.default_tab.setCurrentIndex(max(0, index))
        form.addRow(QLabel(T("Onglet au lancement :")), self.default_tab)
        layout.addWidget(fields)
        self.update_channel = QComboBox()
        self.update_channel.addItem(T("Désactivé"), "disabled")
        self.update_channel.addItem(T("Mise à jour stable"), "stable")
        self.update_channel.addItem(T("Toutes les mises à jour (instable)"), "all")
        form.addRow(QLabel(T("Mises à jour :")), self.update_channel)
        self.update_warning = QLabel(T("Les versions en développement peuvent comporter des bugs."))
        self.update_warning.setWordWrap(True)
        self.update_warning.setStyleSheet("color: #c87518;")
        self.update_warning.hide()
        layout.addWidget(self.update_warning)
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        update_actions = QHBoxLayout()
        self.check_updates = QPushButton(T("Vérifier maintenant"))
        self.install_update = QPushButton(T("Télécharger et installer"))
        self.install_update.hide()
        update_actions.addWidget(self.check_updates)
        update_actions.addWidget(self.install_update)
        update_actions.addStretch()
        layout.addLayout(update_actions)
        version_info = QHBoxLayout()
        self.current_version = QLabel()
        version_info.addWidget(self.current_version)
        self.release_link = QLabel(
            T('<a href="{url}">{label}</a>', url=RELEASE_URL, label=T("Voir les releases"))
        )
        self.release_link.setTextFormat(Qt.TextFormat.RichText)
        self.release_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.release_link.setOpenExternalLinks(True)
        version_info.addWidget(self.release_link)
        version_info.addStretch()
        layout.addLayout(version_info)
        self.hotkeys = HotkeySettings(self)
        layout.addWidget(self.hotkeys)
        self.hotkeys.enabled.toggled.connect(self.resize_to_contents)
        self.game_installations = GameInstallationsPanel(self)
        self.game_installations.configurations_changed.connect(self.resize_to_contents)
        layout.addWidget(self.game_installations)
        buttons = QHBoxLayout()
        self.onboarding_button = QPushButton(T("Assistant de démarrage"))
        self.onboarding_button.setAutoDefault(False)
        buttons.addWidget(self.onboarding_button)
        buttons.addStretch()
        self.close_button = QPushButton(T("Fermer"))
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.opened.emit()
        self.resize_to_contents()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.hidden.emit()

    def resize_to_contents(self) -> None:
        """Schedule sizing after conditional settings fields update their layouts."""
        self._resize_timer.start(0)

    def _fit_configuration_results(self) -> None:
        layout = self._content_layout
        results = self.game_installations.results
        results.setMinimumHeight(0)
        results.setMaximumHeight(270)
        layout.invalidate()
        layout.activate()

        available = self.screen().availableGeometry()
        frame_height = self.frameGeometry().height() - self.height()
        available_height = available.height() - frame_height
        root = self.layout()
        root.activate()
        margins = root.contentsMargins()
        scrollbar_width = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        content_width = self.width() - margins.left() - margins.right() - scrollbar_width
        shell_height = margins.top() + margins.bottom() + root.spacing()
        shell_height += self.close_button.sizeHint().height()
        if self.game_installations.rows:
            other_controls = layout.minimumSize().height() - results.minimumSizeHint().height()
            result_layout = self.game_installations.result_widget.layout()
            panel_margins = self.game_installations.layout().contentsMargins()
            result_width = content_width - panel_margins.left() - panel_margins.right()
            result_width -= 2 * results.frameWidth() + scrollbar_width
            content_height = result_layout.totalHeightForWidth(result_width)
            if content_height < 0:
                content_height = result_layout.sizeHint().height()
            content_height += 2 * results.frameWidth()
            results_height = min(
                270, content_height, available_height - shell_height - other_controls
            )
            results.setFixedHeight(max(results.minimumSizeHint().height(), results_height))
            layout.invalidate()
            layout.activate()

        preferred_height = max(
            layout.minimumSize().height(),
            layout.totalHeightForWidth(content_width),
        )
        self.resize(self.width(), min(shell_height + preferred_height, available_height))
        if self.isVisible() and self.frameGeometry().bottom() > available.bottom():
            self.move(
                self.x(),
                max(available.top(), available.bottom() - self.frameGeometry().height() + 1),
            )
