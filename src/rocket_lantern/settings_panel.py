"""Application preferences grouped into independently scrolling sections."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.game_installations_panel import GameInstallationsPanel
from rocket_lantern.hotkey_settings import HotkeySettings
from rocket_lantern.i18n import Text
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.label_settings import LabelSettings
from rocket_lantern.overlay_settings import OverlaySettings
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTabWidget as QTabWidget
from rocket_lantern.translated_widgets import binding
from rocket_lantern.updates import RELEASE_URL


class SettingsPanel(QDialog):
    """Keep general preferences, game setup, overlay and shortcuts separate."""

    opened = Signal()
    hidden = Signal()

    def __init__(
        self,
        port: int,
        language: str,
        default_tab: str,
        parent: QWidget,
        catalog: LabelCatalog | None = None,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        if self.catalog is None:
            self.catalog = LabelCatalog(parent=self)
        self.setWindowTitle(T("Paramètres"))
        self.resize(560, 360)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_current_section)
        root = QVBoxLayout(self)
        self._title = QLabel(T("Paramètres"))
        self._title.setStyleSheet("font-size: 22px; font-weight: 600;")
        root.addWidget(self._title)
        self.sections = QTabWidget()
        self.sections.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        root.addWidget(self.sections, 1)
        self.general_section, general = self._add_section(T("Général"))
        self._build_general(general, port, language, default_tab)
        self.game_section, game = self._add_section("Rocket League")
        self.game_installations = GameInstallationsPanel(self)
        game.addWidget(self.game_installations)
        self.onboarding_button = QPushButton(T("Assistant de démarrage"))
        self.onboarding_button.setAutoDefault(False)
        game.addWidget(self.onboarding_button)
        self.game_installations.configurations_changed.connect(self.resize_to_contents)
        self.overlay_section, overlay = self._add_section(T("Overlay"))
        self.overlay_tabs = QTabWidget()
        self.overlay = OverlaySettings()
        self.boost_overlay = OverlaySettings(boost=True)
        self.overlay_tabs.addTab(self.overlay, T("Bilan W/L"))
        self.overlay_tabs.addTab(self.boost_overlay, T("Boost des coéquipiers"))
        overlay.addWidget(self.overlay_tabs)
        self.overlay_display_hint = QLabel(
            T(
                "Si un overlay n’apparaît pas en plein écran, passez Rocket League "
                "en mode Sans bords ou Fenêtré."
            )
        )
        self.overlay_display_hint.setWordWrap(True)
        overlay.addWidget(self.overlay_display_hint)
        self.overlay_tabs.currentChanged.connect(self.resize_to_contents)
        self.labels_section, labels = self._add_section(T("Étiquettes"))
        self.labels = LabelSettings(self.catalog, self)
        labels.addWidget(self.labels)
        self.shortcuts_section, shortcuts = self._add_section(T("Raccourcis"))
        self.hotkeys = HotkeySettings(self, self.catalog)
        shortcuts.addWidget(self.hotkeys)
        self.hotkeys.enabled.toggled.connect(self.resize_to_contents)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton(T("Fermer"))
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)
        self.sections.currentChanged.connect(self.resize_to_contents)
        binding(self).callbacks.append(self.resize_to_contents)

    def _add_section(self, title: str | Text) -> tuple[QScrollArea, QVBoxLayout]:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(content)
        self.sections.addTab(area, title)
        return area, layout

    def _build_general(
        self, layout: QVBoxLayout, port: int, language: str, default_tab: str
    ) -> None:
        fields = QWidget()
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
        self.default_tab.setCurrentIndex(max(0, self.default_tab.findData(default_tab)))
        form.addRow(QLabel(T("Onglet au lancement :")), self.default_tab)
        self.update_channel = QComboBox()
        self.update_channel.addItem(T("Désactivé"), "disabled")
        self.update_channel.addItem(T("Mise à jour stable"), "stable")
        self.update_channel.addItem(T("Toutes les mises à jour (instable)"), "all")
        form.addRow(QLabel(T("Mises à jour :")), self.update_channel)
        layout.addWidget(fields)
        self.update_warning = QLabel(T("Les versions en développement peuvent comporter des bugs."))
        self.update_warning.setWordWrap(True)
        self.update_warning.setStyleSheet("color: #c87518;")
        self.update_warning.hide()
        layout.addWidget(self.update_warning)
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        actions = QHBoxLayout()
        self.check_updates = QPushButton(T("Vérifier maintenant"))
        self.install_update = QPushButton(T("Télécharger et installer"))
        self.install_update.hide()
        actions.addWidget(self.check_updates)
        actions.addWidget(self.install_update)
        actions.addStretch()
        layout.addLayout(actions)
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

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.opened.emit()
        self.resize_to_contents()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.hidden.emit()

    def resize_to_contents(self) -> None:
        """Resize only for the visible section after its conditional controls settle."""
        self._resize_timer.start(0)

    def _fit_current_section(self) -> None:
        area = self.sections.currentWidget()
        layout = area.widget().layout()
        layout.invalidate()
        layout.activate()
        available = self.screen().availableGeometry()
        frame_height = self.frameGeometry().height() - self.height()
        available_height = max(1, available.height() - frame_height)
        margins = self.layout().contentsMargins()
        shell = margins.top() + margins.bottom() + 3 * self.layout().spacing()
        shell += self._title.sizeHint().height() + self.close_button.sizeHint().height()
        shell += self.sections.tabBar().sizeHint().height() + 4
        scrollbar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        width = max(1, self.width() - margins.left() - margins.right() - scrollbar - 4)
        if area is self.game_section:
            self._fit_game_results(layout, width, available_height - shell)
        preferred = max(layout.minimumSize().height(), layout.totalHeightForWidth(width), 140)
        self.resize(self.width(), min(shell + preferred, available_height))
        if self.isVisible() and self.frameGeometry().bottom() > available.bottom():
            self.move(
                self.x(),
                max(available.top(), available.bottom() - self.frameGeometry().height() + 1),
            )

    def _fit_game_results(self, layout: QVBoxLayout, width: int, available: int) -> None:
        results = self.game_installations.results
        results.setMinimumHeight(0)
        results.setMaximumHeight(270)
        layout.invalidate()
        layout.activate()
        if not self.game_installations.rows:
            return
        other = layout.minimumSize().height() - results.minimumSizeHint().height()
        panel_margins = self.game_installations.layout().contentsMargins()
        result_width = width - panel_margins.left() - panel_margins.right()
        result_width -= 2 * results.frameWidth()
        result_layout = self.game_installations.result_widget.layout()
        height = result_layout.totalHeightForWidth(max(1, result_width))
        if height < 0:
            height = result_layout.sizeHint().height()
        height += 2 * results.frameWidth()
        results.setFixedHeight(
            max(results.minimumSizeHint().height(), min(270, height, available - other))
        )
        layout.invalidate()
        layout.activate()
