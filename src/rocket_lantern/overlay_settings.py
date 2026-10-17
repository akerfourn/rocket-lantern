"""Independent, opt-in controls for the external desktop overlays."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QToolButton, QVBoxLayout, QWidget

from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import set_text


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
        description = T(
            "Les icônes indiquent les victoires, les défaites et leur différence. "
            "Le bilan suit les filtres de l’application. Utilisez le mode Sans bords "
            "dans Rocket League. L’overlay laisse passer les clics et reste désactivé "
            "au lancement ; sa position est mémorisée."
        )
        if boost:
            description = T(
                "Uniquement les coéquipiers du joueur sélectionné, jamais son propre boost. "
                "Utilisez le mode Sans bords dans Rocket League. Cet overlay a sa propre "
                "position et reste désactivé au lancement. Sans données récentes, il se masque."
            )
        hint = QLabel(description)
        hint.setWordWrap(True)
        fields.addRow(hint)
        self.diagnostics = QToolButton()
        set_text(self.diagnostics, "text", T("Diagnostic"), self.diagnostics.setText)
        self.diagnostics.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.diagnostics.setArrowType(Qt.ArrowType.RightArrow)
        self.diagnostics.setAutoRaise(True)
        self.diagnostics.setCheckable(True)
        fields.addRow(self.diagnostics)
        self.diagnostic_fields = QWidget()
        diagnostic_fields = QVBoxLayout(self.diagnostic_fields)
        diagnostic_fields.setContentsMargins(0, 0, 0, 0)
        self.native_status = QLabel()
        self.native_status.setWordWrap(True)
        diagnostic_fields.addWidget(self.native_status)
        self.copy_diagnostic = QPushButton(T("Copier le diagnostic de l’overlay"))
        self.copy_diagnostic.setAutoDefault(False)
        diagnostic_fields.addWidget(self.copy_diagnostic)
        self.diagnostic_fields.hide()
        self.diagnostics.toggled.connect(self._show_diagnostics)
        fields.addRow(self.diagnostic_fields)
        layout.addWidget(self.options)

    def _show_diagnostics(self, visible: bool) -> None:
        arrow = Qt.ArrowType.RightArrow
        if visible:
            arrow = Qt.ArrowType.DownArrow
        self.diagnostics.setArrowType(arrow)
        self.diagnostic_fields.setVisible(visible)


def boost_warning() -> DisplayText:
    return T(
        "Risque de bannissement : afficher le boost des coéquipiers peut être considéré "
        "comme un avantage compétitif par Epic/Psyonix. RocketLantern ne garantit ni "
        "l’autorisation de cet usage ni l’absence de sanction. Vérifiez les règles en vigueur "
        "avant de l’activer."
    )
