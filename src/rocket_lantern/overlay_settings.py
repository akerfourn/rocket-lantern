"""Independent, opt-in controls for the external desktop overlays."""

from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class OverlaySettings(QWidget):
    def __init__(self, boost: bool = False) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = T("Afficher l’overlay")
        if boost:
            label = T("Afficher le boost des coéquipiers")
        self.enabled = QCheckBox(label)
        layout.addWidget(self.enabled)
        if boost:
            self.warning = QLabel(boost_warning())
            self.warning.setWordWrap(True)
            self.warning.setStyleSheet("color: #e6a351;")
            layout.addWidget(self.warning)
        self.options = QWidget()
        fields = QFormLayout(self.options)
        fields.setContentsMargins(0, 0, 0, 0)
        self.monitor = QComboBox()
        fields.addRow(QLabel(T("Écran :")), self.monitor)
        self.corner = QComboBox()
        self.corner.addItem(T("En haut à gauche"), "top_left")
        self.corner.addItem(T("En haut à droite"), "top_right")
        self.corner.addItem(T("En bas à gauche"), "bottom_left")
        self.corner.addItem(T("En bas à droite"), "bottom_right")
        self.corner.addItem(T("Personnalisée"), "custom")
        fields.addRow(QLabel(T("Position :")), self.corner)
        self.place_button = QPushButton(T("Positionner l’overlay…"))
        self.place_button.setAutoDefault(False)
        fields.addRow(self.place_button)
        layout.addWidget(self.options)


def boost_warning() -> DisplayText:
    return T(
        "Risque de bannissement : afficher le boost des coéquipiers peut être considéré "
        "comme un avantage compétitif par Epic/Psyonix. RocketLantern ne garantit ni "
        "l’autorisation de cet usage ni l’absence de sanction. Vérifiez les règles en vigueur "
        "avant de l’activer."
    )
