"""Read-only session overview with per-match metadata and observed player stats."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.match_detail_dialog import MatchDetailDialog, display, score_label, table
from rl_winloose.playlists import playlist_label
from rl_winloose.statistics_panel import StatisticsPanel
from rl_winloose.storage import MatchStore, Summary

OUTCOMES = {"win": "Victoire", "loss": "Défaite", "unknown": "Inconnu"}
STAT_FIELDS = ("score", "goals", "shots", "assists", "saves", "touches", "car_touches", "demos")


def local_date(value: str) -> str:
    """Format stored timestamps in the user's local timezone."""
    return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M:%S")


class SessionDetailDialog(QDialog):
    """Show the complete session independently of the main view's playlist filter."""

    def __init__(
        self, store: MatchStore, player_id: str, session_id: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.player_id = player_id
        self.setWindowTitle(f"Détail de la session #{session_id}")
        self.resize(1100, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        session = store.session_detail(player_id, session_id)
        if session is None:
            layout.addWidget(QLabel("Session indisponible pour le joueur sélectionné."))
            return
        self.rows = store.session_matches(player_id, session_id)
        summary = Summary(
            sum(row["outcome"] == "win" for row in self.rows),
            sum(row["outcome"] == "loss" for row in self.rows),
            sum(row["outcome"] == "unknown" for row in self.rows),
        )
        balance = summary.wins - summary.losses
        balance_text = str(balance)
        if balance > 0:
            balance_text = f"+{balance}"
        self.metadata = QLabel(
            f"Session #{session_id} · Session complète, toutes playlists\n"
            f"Début : {local_date(session['started_at'])} · "
            f"Dernière activité : {local_date(session['last_activity_at'])}\n"
            f"{len(self.rows)} matchs · {summary.wins} victoires · "
            f"{summary.losses} défaites ({balance_text}) · "
            f"{summary.win_rate:.1f} % de victoires · {summary.unknown} inconnus"
        )
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        self.tabs = QTabWidget()
        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.addWidget(QLabel("Statistiques cumulées du joueur sélectionné"))
        self.statistics = StatisticsPanel()
        self.statistics.update_rows(self.rows)
        overview_layout.addWidget(self.statistics)
        overview_layout.addStretch()
        self.tabs.addTab(overview, "Synthèse")
        match_rows = []
        stat_rows = []
        for row in self.rows:
            overtime = "—"
            if row["overtime"] is not None:
                overtime = "Oui" if row["overtime"] else "Non"
            quality = "Détails indisponibles"
            if row["observed_at"] is not None:
                quality = "Dernier état observé (partiel)"
                if row["final_observed"]:
                    quality = "État de fin observé"
            date = local_date(row["ended_at"])
            match_rows.append(
                [
                    date,
                    OUTCOMES[row["outcome"]],
                    playlist_label(row["playlist"]),
                    display(row["arena"]),
                    "",
                    overtime,
                    quality,
                ]
            )
            stat_rows.append([date] + [display(row[key]) for key in STAT_FIELDS])
        self.matches = table(
            [
                "Résultat observé le",
                "Résultat",
                "Type de partie",
                "Arène",
                "Score B–O",
                "Prolongation",
                "Disponibilité",
            ],
            match_rows,
        )
        for column in (2, 6):
            self.matches.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        for index, row in enumerate(self.rows):
            label = score_label(row["blue_score"], row["orange_score"], row["team"], compact=True)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.matches.setCellWidget(index, 4, label)
        self.stats = table(
            [
                "Résultat observé le",
                "Points",
                "Buts",
                "Tirs",
                "Passes",
                "Arrêts",
                "Touches",
                "Contacts",
                "Démos",
            ],
            stat_rows,
        )
        self.stats.horizontalHeaderItem(7).setToolTip("Contacts entre voitures")
        for column in range(1, self.stats.columnCount()):
            self.stats.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
            for row in range(self.stats.rowCount()):
                self.stats.item(row, column).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (self.matches, self.stats):
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            widget.cellClicked.connect(self._open_match)
            widget.cellActivated.connect(self._open_match)
        self.tabs.addTab(self.matches, "Matchs et métadonnées")
        self.tabs.addTab(self.stats, "Statistiques par match")
        layout.addWidget(self.tabs, 1)
        hint = "Un clic sur un match ouvre les statistiques de tous ses joueurs et ses événements."
        if len(self.rows) == 0:
            hint = "Cette session ne contient encore aucun match enregistré."
        self.hint = QLabel(
            f"{hint}\n— : donnée non reçue ; 0 : valeur reçue égale à zéro.\n"
            "Les statistiques peuvent être partielles ; les événements couvrent seulement "
            "la période de connexion. Cette fenêtre est un instantané à son ouverture."
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Fermer")
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _open_match(self, row: int, column: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        existing = self.findChild(MatchDetailDialog)
        if existing is not None and existing.isVisible():
            return
        dialog = MatchDetailDialog(self.store, self.rows[row]["match_id"], self, self.player_id)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
