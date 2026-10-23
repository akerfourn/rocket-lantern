"""Independent scoreboard HUD preferences alongside the existing desktop overlays."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal

from rocket_lantern.i18n import text as T
from rocket_lantern.overlay_settings import OverlaySettings
from rocket_lantern.scoreboard_overlay_scope import ScoreboardScope
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class ScoreboardOverlaySettings(OverlaySettings):
    players_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__(summary_content=False)
        self.players_scope = QComboBox()
        self.players_scope.addItem(T("Tous les joueurs"), ScoreboardScope.ALL.value)
        self.players_scope.addItem(T("Mon équipe"), ScoreboardScope.TEAM.value)
        self.players_scope.addItem(T("Équipe adverse"), ScoreboardScope.OPPONENTS.value)
        self.players_scope.addItem(T("Mon joueur uniquement"), ScoreboardScope.PLAYER.value)
        self.options.layout().insertRow(0, QLabel(T("Joueurs affichés :")), self.players_scope)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.players_scope.currentIndexChanged.connect(self._players_changed)

    def set_players_scope(self, scope: ScoreboardScope) -> None:
        with QSignalBlocker(self.players_scope):
            self.players_scope.setCurrentIndex(self.players_scope.findData(scope.value))

    def _players_changed(self) -> None:
        self.players_changed.emit(self.players_scope.currentData())
