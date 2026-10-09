"""Read-only structured summary of a saved match."""

from datetime import datetime
from sqlite3 import Row

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.i18n import DateText, DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.playlists import playlist_text as playlist_label
from rocket_lantern.storage import MatchStore
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import TranslatedTabWidget as QTabWidget
from rocket_lantern.translated_widgets import set_text


def display(value: object) -> str:
    """Distinguish missing information from zero."""
    if value is None:
        return "—"
    return str(value)


def score_label(
    blue: int | None,
    orange: int | None,
    team: int | None,
    *,
    compact: bool = False,
    observed: bool = False,
) -> QLabel:
    """Emphasize the player's score while keeping the blue/orange order explicit."""
    blue_text = display(blue)
    orange_text = display(orange)
    if team == 0:
        blue_text = f"<b><u>{blue_text}</u></b>"
    elif team == 1:
        orange_text = f"<b><u>{orange_text}</u></b>"
    text = T(
        "Bleus {blue_text} – {orange_text} Oranges", blue_text=blue_text, orange_text=orange_text
    )
    if compact:
        text = f"{blue_text} – {orange_text}"
    if observed:
        text = T("{score} (observé)", score=text)
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if team in (0, 1):
        label.setToolTip(T("Le score souligné correspond à l’équipe du joueur sélectionné."))
    return label


def table(headers: list[DisplayText], rows: list[list[DisplayText]]) -> QTableWidget:
    """Build a compact noneditable table of selected persisted fields."""
    widget = QTableWidget(len(rows), len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.setStyleSheet(
        "QTableWidget::item { padding: 0 8px; }QHeaderView::section { padding: 5px 8px; }"
    )
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(34)
    for index, values in enumerate(rows):
        for column, value in enumerate(values):
            widget.setItem(index, column, QTableWidgetItem(value))
    return widget


class MatchDetailDialog(QDialog):
    """Present match metadata, participant totals and important events."""

    def __init__(
        self,
        store: MatchStore,
        guid: str,
        parent: QWidget | None = None,
        player_id: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(T("Détail du match"))
        self.resize(1050, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        detail = store.detail(guid)
        if detail is None or detail["observed_at"] is None:
            layout.addWidget(QLabel(T("Ancien match : statistiques détaillées indisponibles.")))
            layout.addStretch()
            layout.addWidget(self._close_button())
            return
        team = store.player_team(guid, player_id)
        self.score = score_label(detail["blue_score"], detail["orange_score"], team)
        self.score.setStyleSheet("font-size: 28px; padding: 8px; font-weight: 600;")
        layout.addWidget(self.score)
        context = QLabel(
            T(
                "{playlist} · {arena}",
                playlist=playlist_label(detail["playlist"]),
                arena=display(detail["arena"]),
            )
        )
        context.setTextFormat(Qt.TextFormat.PlainText)
        context.setWordWrap(True)
        context.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(context)
        quality = T("Dernier état observé · données partielles")
        if detail["final_observed"]:
            quality = T("État de fin observé · événements limités à la période de connexion")
        self.quality = QLabel(quality)
        self.quality.setWordWrap(True)
        layout.addWidget(self.quality)
        self.tabs = QTabWidget()
        participants = store.participants(guid)
        self.players = self._player_table(participants, player_id)
        self.tabs.addTab(self.players, T("Joueurs ({count})", count=len(participants)))
        self.events = self._event_table(store.events(guid))
        self.tabs.addTab(self.events, T("Événements ({value})", value=self.events.rowCount()))
        self.tabs.addTab(self._information(detail), T("Informations"))
        layout.addWidget(self.tabs, 1)
        self.player_hint = QLabel(T("Joueur sélectionné non présent dans les données de ce match."))
        for player in participants:
            if player["primary_id"] == player_id:
                self.player_hint.setText(
                    T(
                        "{name} : ligne en surbrillance · score de son équipe souligné.",
                        name=player["name"],
                    )
                )
                break
        self.player_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.player_hint.setWordWrap(True)
        layout.addWidget(self.player_hint)
        hint = QLabel(
            T(
                "Dernières valeurs reçues pour chaque joueur, y compris ceux "
                "partis du match. — : donnée absente ; 0 : zéro reçu. Vitesses en "
                "unités Unreal/s."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self._close_button())

    def _player_table(self, participants: list[Row], player_id: str) -> QTableWidget:
        rows = []
        for player in participants:
            name = player["name"]
            if player["primary_id"] == player_id:
                name = T("{name} (sélectionné)", name=name)
            rows.append(
                [name, {0: T("Bleue"), 1: T("Orange")}.get(player["team"], "—")]
                + [
                    display(player[key])
                    for key in (
                        "score",
                        "goals",
                        "shots",
                        "assists",
                        "saves",
                        "touches",
                        "demos",
                        "car_touches",
                    )
                ]
            )
        widget = table(
            [
                T("Joueur"),
                T("Équipe"),
                T("Points"),
                T("Buts"),
                T("Tirs"),
                T("Passes"),
                T("Arrêts"),
                T("Touches"),
                T("Démos"),
                T("Contacts"),
            ],
            rows,
        )
        widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        widget.horizontalHeaderItem(9).setToolTip(T("Contacts entre voitures"))
        for index, player in enumerate(participants):
            widget.item(index, 0).setData(Qt.ItemDataRole.UserRole, player["primary_id"])
            for column in range(1, widget.columnCount()):
                widget.item(index, column).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if player["primary_id"] != player_id:
                continue
            for column in range(widget.columnCount()):
                item = widget.item(index, column)
                item.setBackground(widget.palette().highlight())
                item.setForeground(widget.palette().highlightedText())
                font = item.font()
                font.setBold(True)
                item.setFont(font)
        return widget

    def _event_table(self, events: list[Row]) -> QTableWidget:
        rows = []
        for event in events:
            kind = event["kind"]
            if kind == "GoalScored":
                kind = T("But")
            elif kind == "CrossbarHit":
                kind = T("Barre")
            clock = display(event["time_seconds"])
            if event["overtime"]:
                clock = T("Prolongation {clock}", clock=clock)
            position = "—"
            if all(event[key] is not None for key in ("x", "y", "z")):
                position = f"{event['x']}, {event['y']}, {event['z']}"
            rows.append(
                [
                    clock,
                    kind,
                    display(event["actor_name"]),
                    display(event["secondary_name"]),
                    display(event["speed"]),
                    position,
                    display(event["round_seconds"]),
                ]
            )
        return table(
            [
                T("Horloge (s)"),
                T("Événement"),
                T("Joueur"),
                T("Passeur / cible"),
                T("Vitesse"),
                T("Position"),
                T("Manche (s)"),
            ],
            rows,
        )

    def _information(self, detail: Row) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(14)
        overtime = "—"
        if detail["overtime"] is not None:
            overtime = T("Oui") if detail["overtime"] else T("Non")
        observed_at = datetime.fromisoformat(detail["observed_at"]).astimezone()
        for title, value in (
            (T("Type de partie"), playlist_label(detail["playlist"])),
            (T("Arène"), display(detail["arena"])),
            (T("Prolongation"), overtime),
            (T("Dernière observation"), DateText(observed_at, seconds=True)),
            (T("Identifiant API du match"), detail["guid"]),
            (T("Identifiant local"), str(detail["id"])),
        ):
            label = QLabel(value)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            layout.addRow(QLabel(title), label)
        return widget

    def _close_button(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button = buttons.button(QDialogButtonBox.StandardButton.Close)
        set_text(button, "text", T("Fermer"), button.setText)
        buttons.rejected.connect(self.reject)
        return buttons
