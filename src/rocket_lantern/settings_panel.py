"""Application preferences, separated from the match views."""

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QSpinBox, QVBoxLayout, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class SettingsPanel(QDialog):
    """Expose connection, language and startup preferences."""

    def __init__(self, port: int, language: str, default_tab: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(T("Paramètres"))
        self.resize(460, 180)
        layout = QVBoxLayout(self)
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
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton(T("Fermer"))
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
