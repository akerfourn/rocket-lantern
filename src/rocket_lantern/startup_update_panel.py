"""Manual update recovery controls that never read or write the settings database."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout

from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.updates import RELEASE_URL


class StartupUpdatePanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__(T("Mises à jour"))
        layout = QVBoxLayout(self)
        version_row = QHBoxLayout()
        self.current_version = QLabel()
        version_row.addWidget(self.current_version)
        version_row.addStretch()
        self.release_link = QLabel(
            T('<a href="{url}">{label}</a>', url=RELEASE_URL, label=T("Voir les releases"))
        )
        self.release_link.setTextFormat(Qt.TextFormat.RichText)
        self.release_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.release_link.setOpenExternalLinks(True)
        palette = self.release_link.palette()
        palette.setColor(QPalette.ColorRole.Link, palette.color(QPalette.ColorRole.WindowText))
        self.release_link.setPalette(palette)
        version_row.addWidget(self.release_link)
        layout.addLayout(version_row)
        self.update_channel = QComboBox()
        self.update_channel.addItem(T("Mise à jour stable"), "stable")
        self.update_channel.addItem(T("Toutes les mises à jour (instable)"), "all")
        self.check_updates = QPushButton(T("Vérifier maintenant"))
        self.check_updates.setAutoDefault(False)
        channel_row = QHBoxLayout()
        channel_row.addWidget(self.update_channel, 1)
        channel_row.addWidget(self.check_updates)
        form = QFormLayout()
        channel_label = QLabel(T("Mises à jour :"))
        channel_label.setBuddy(self.update_channel)
        form.addRow(channel_label, channel_row)
        layout.addLayout(form)
        self.update_warning = QLabel(T("Les versions en développement peuvent comporter des bugs."))
        self.update_warning.setWordWrap(True)
        self.update_warning.setStyleSheet("color: #c87518;")
        self.update_warning.hide()
        layout.addWidget(self.update_warning)
        self.update_status = QLabel()
        self.update_status.setTextFormat(Qt.TextFormat.PlainText)
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        self.install_update = QPushButton(T("Télécharger et installer"))
        self.install_update.setAutoDefault(False)
        self.install_update.hide()
        layout.addWidget(self.install_update, 0, Qt.AlignmentFlag.AlignLeft)
