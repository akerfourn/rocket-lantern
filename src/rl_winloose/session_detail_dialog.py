"""Read-only session overview with per-match metadata and observed player stats."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.match_detail_dialog import MatchDetailDialog, display, table
from rl_winloose.playlists import playlist_label
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
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
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
            f"Début : {local_date(session['started_at'])}\n"
            f"Dernière activité enregistrée : {local_date(session['last_activity_at'])}\n"
            f"{len(self.rows)} matchs · {summary.wins} victoires · "
            f"{summary.losses} défaites ({balance_text}) · "
            f"{summary.win_rate:.1f} % de victoires · {summary.unknown} inconnus"
        )
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        self.tabs = QTabWidget()
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
                    f"{display(row['blue_score'])} – {display(row['orange_score'])}",
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
        self.stats = table(
            [
                "Résultat observé le",
                "Points",
                "Buts",
                "Tirs",
                "Passes",
                "Arrêts",
                "Touches",
                "Contacts voitures",
                "Démos",
            ],
            stat_rows,
        )
        self.matches.cellDoubleClicked.connect(self._open_match)
        self.stats.cellDoubleClicked.connect(self._open_match)
        self.tabs.addTab(self.matches, "Matchs et métadonnées")
        self.tabs.addTab(self.stats, "Statistiques du joueur sélectionné")
        layout.addWidget(self.tabs)
        hint = "Double-clique sur un match pour voir ses joueurs et événements enregistrés."
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
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _open_match(self, row: int, column: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        dialog = MatchDetailDialog(self.store, self.rows[row]["match_id"], self, self.player_id)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
