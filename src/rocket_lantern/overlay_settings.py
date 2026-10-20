"""Independent, opt-in controls for the external desktop overlays."""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from rocket_lantern.boost_overlay_mode import BoostOverlayMode
from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.summary_overlay_settings import SummaryOverlaySettings
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class OverlaySettings(QWidget):
    activation_changed = Signal(str)

    def __init__(self, boost: bool = False, catalog: LabelCatalog | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inactive_value = "0"
        self.activation_values = ("0", "1")
        if boost:
            self.inactive_value = BoostOverlayMode.NEVER.value
            self.activation_values = tuple(mode.value for mode in BoostOverlayMode)
            self.scope = QComboBox()
            self.scope.addItem(T("Jamais"), BoostOverlayMode.NEVER.value)
            self.scope.addItem(T("Parties privées uniquement"), BoostOverlayMode.PRIVATE.value)
            self.scope.addItem(T("Toutes les parties"), BoostOverlayMode.ALL.value)
            activation = QFormLayout()
            activation.addRow(QLabel(T("Affichage :")), self.scope)
            layout.addLayout(activation)
            self.activation_control = self.scope
            self.scope.currentIndexChanged.connect(self._activation_changed)
        else:
            self.enabled = QCheckBox(T("Afficher l’overlay"))
            layout.addWidget(self.enabled)
            self.activation_control = self.enabled
            self.enabled.toggled.connect(self._activation_changed)
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
        if not boost:
            if catalog is None:
                catalog = LabelCatalog(parent=self)
            self.content = SummaryOverlaySettings(catalog)
            layout.addWidget(self.content)

    def activation_value(self) -> str:
        if isinstance(self.activation_control, QComboBox):
            return self.activation_control.currentData()
        if self.enabled.isChecked():
            return "1"
        return "0"

    def activation_enabled(self) -> bool:
        return self.activation_value() != self.inactive_value

    def set_activation_value(self, value: str) -> None:
        """Synchronize restored preferences without triggering a settings write."""
        with QSignalBlocker(self.activation_control):
            if isinstance(self.activation_control, QComboBox):
                self.activation_control.setCurrentIndex(self.activation_control.findData(value))
            else:
                self.enabled.setChecked(value == "1")

    def _activation_changed(self) -> None:
        self.activation_changed.emit(self.activation_value())


def boost_warning() -> DisplayText:
    return T(
        "Risque de bannissement : afficher le boost des coéquipiers peut être considéré "
        "comme un avantage compétitif par Epic/Psyonix. RocketLantern ne garantit ni "
        "l’autorisation de cet usage ni l’absence de sanction. Vérifiez les règles en vigueur "
        "avant de l’activer."
    )
