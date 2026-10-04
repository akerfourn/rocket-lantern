"""Read-only structured summary of a saved match."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.storage import MatchStore


def display(value: object) -> str:
    """Distinguish missing information from zero."""
    if value is None:
        return "—"
    return str(value)


def score_label(blue: int | None, orange: int | None, team: int | None) -> QLabel:
    """Emphasize the player's score while keeping the blue/orange order explicit."""
    blue_text = display(blue)
    orange_text = display(orange)
    if team == 0:
        blue_text = f"<b>{blue_text}</b>"
    elif team == 1:
        orange_text = f"<b>{orange_text}</b>"
    label = QLabel(f"Bleus {blue_text} – {orange_text} Oranges")
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if team in (0, 1):
        label.setToolTip("Le score en gras correspond à l’équipe du joueur sélectionné.")
    return label


def table(headers: list[str], rows: list[list[str]]) -> QTableWidget:
    """Build a compact noneditable table of selected persisted fields."""
    widget = QTableWidget(len(rows), len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.verticalHeader().hide()
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
        self.setWindowTitle("Détail du match")
        self.resize(1050, 650)
        layout = QVBoxLayout(self)
        detail = store.detail(guid)
        if detail is None or detail["observed_at"] is None:
            layout.addWidget(QLabel("Ancien match : statistiques détaillées indisponibles."))
            return
        team = store.player_team(guid, player_id)
        self.score = score_label(detail["blue_score"], detail["orange_score"], team)
        self.score.setStyleSheet("font-size: 22px; padding: 8px;")
        layout.addWidget(self.score)
        if team in (0, 1):
            team_name = "bleue"
            if team == 1:
                team_name = "orange"
            layout.addWidget(QLabel(f"Joueur sélectionné : équipe {team_name} (score en gras)."))
        quality = "Dernier état observé · données partielles"
        if detail["final_observed"]:
            quality = "État de fin observé · événements limités à la période de connexion"
        overtime = "Indisponible"
        if detail["overtime"] is not None:
            overtime = "Non"
            if detail["overtime"]:
                overtime = "Oui"
        metadata = QLabel(
            f"Arène : {display(detail['arena'])} · Prolongation : {overtime}\n"
            f"{quality}\nStatistiques : dernières valeurs reçues pour chaque joueur.\n"
            f"Match API : {guid} · ID local : {detail['id']}"
        )
        metadata.setTextFormat(Qt.TextFormat.PlainText)
        metadata.setWordWrap(True)
        layout.addWidget(metadata)
        players = []
        for player in store.participants(guid):
            team = "Bleue"
            if player["team"] == 1:
                team = "Orange"
            players.append(
                [player["name"], team]
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
                    )
                ]
            )
        self.players = table(
            ["Joueur", "Équipe", "Points", "Buts", "Tirs", "Passes", "Arrêts", "Touches", "Démos"],
            players,
        )
        layout.addWidget(self.players)
        layout.addWidget(QLabel("Buts et événements importants · vitesses en unités Unreal/s"))
        events = []
        for event in store.events(guid):
            kind = event["kind"]
            if kind == "GoalScored":
                kind = "But"
            elif kind == "CrossbarHit":
                kind = "Barre"
            clock = display(event["time_seconds"])
            if event["overtime"]:
                clock = f"Prolongation {clock}"
            position = "—"
            if all(event[key] is not None for key in ("x", "y", "z")):
                position = f"{event['x']}, {event['y']}, {event['z']}"
            events.append(
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
        self.events = table(
            [
                "Horloge (s)",
                "Événement",
                "Joueur",
                "Passeur / cible",
                "Vitesse",
                "Position",
                "Manche (s)",
            ],
            events,
        )
        layout.addWidget(self.events)
