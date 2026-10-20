"""A compact accessible star for one player's bookmark state."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QToolButton, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import set_text, tooltip


@lru_cache(maxsize=1)
def favorite_icon() -> QIcon:
    assets = Path(__file__).parent / "assets"
    icon = QIcon()
    icon.addFile(str(assets / "star-outline.svg"), state=QIcon.State.Off)
    icon.addFile(str(assets / "star-filled.svg"), state=QIcon.State.On)
    return icon


class FavoritePlayerButton(QToolButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setIcon(favorite_icon())
        self.setCheckable(True)
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(26, 26)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_player("", "", False)

    def set_player(self, primary_id: str, name: str, favorite: bool) -> None:
        self.setChecked(favorite)
        self.setEnabled(primary_id != "")
        description = T("Favoris")
        if primary_id:
            description = T("Ajouter {player} aux favoris", player=name)
            if favorite:
                description = T("Retirer {player} des favoris", player=name)
        tooltip(self, description)
        set_text(self, "accessibleName", description, self.setAccessibleName)
