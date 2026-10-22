"""Read-only session overview with per-match metadata and observed player stats."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QHeaderView, QVBoxLayout, QWidget

from rocket_lantern.i18n import DateText
from rocket_lantern.i18n import text as T
from rocket_lantern.match_detail_dialog import MatchDetailDialog, display, score_label, table
from rocket_lantern.playlists import playlist_text as playlist_label
from rocket_lantern.statistics_panel import StatisticsPanel
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTabWidget as QTabWidget
from rocket_lantern.translated_widgets import set_text

OUTCOMES = {"win": T("Victoire"), "loss": T("Défaite"), "unknown": T("Inconnu")}
STAT_FIELDS = ("score", "goals", "shots", "assists", "saves", "touches", "car_touches", "demos")


def local_date(value: str) -> DateText:
    """Format stored timestamps in the user's local timezone."""
    return DateText(datetime.fromisoformat(value), seconds=True)


class SessionDetailDialog(QDialog):
    """Show the complete session independently of the main view's playlist filter."""

    def __init__(
        self, store: MatchStore, player_id: str, session_id: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.player_id = player_id
        self.setWindowTitle(T("Détail de la session #{session_id}", session_id=session_id))
        self.resize(1100, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        session = store.session_detail(player_id, session_id)
        if session is None:
            layout.addWidget(QLabel(T("Session indisponible pour le joueur sélectionné.")))
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
            T(
                "Session #{session_id} · Session complète, toutes playlists\n"
                "Début : {date} · Dernière activité : {date_2}\n"
                "{count} matchs · {wins} victoires · {losses} défaites "
                "({balance_text}) · {win_rate:.1f} % de victoires · {unknown} "
                "inconnus",
                session_id=session_id,
                date=local_date(session["started_at"]),
                date_2=local_date(session["last_activity_at"]),
                count=len(self.rows),
                wins=summary.wins,
                losses=summary.losses,
                balance_text=balance_text,
                win_rate=summary.win_rate,
                unknown=summary.unknown,
            )
        )
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        self.tabs = QTabWidget()
        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.addWidget(QLabel(T("Moyennes par match du joueur sélectionné")))
        self.statistics = StatisticsPanel()
        self.statistics.update_rows(self.rows)
        overview_layout.addWidget(self.statistics)
        overview_layout.addStretch()
        self.tabs.addTab(overview, T("Synthèse"))
        match_rows = []
        stat_rows = []
        for row in self.rows:
            overtime = "—"
            if row["overtime"] is not None:
                overtime = T("Oui") if row["overtime"] else T("Non")
            quality = T("Détails indisponibles")
            if row["observed_at"] is not None:
                quality = T("Dernier état observé (partiel)")
                if row["final_observed"]:
                    quality = T("État de fin observé")
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
                T("Résultat observé le"),
                T("Résultat"),
                T("Type de partie"),
                T("Arène"),
                T("Score B–O"),
                T("Prolongation"),
                T("Disponibilité"),
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
                T("Résultat observé le"),
                T("Points"),
                T("Buts"),
                T("Tirs"),
                T("Passes"),
                T("Arrêts"),
                T("Touches"),
                T("Contacts"),
                T("Démos"),
            ],
            stat_rows,
        )
        self.stats.horizontalHeaderItem(7).setToolTip(T("Contacts entre voitures"))
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
        self.tabs.addTab(self.matches, T("Matchs et métadonnées"))
        self.tabs.addTab(self.stats, T("Statistiques par match"))
        layout.addWidget(self.tabs, 1)
        hint = T(
            "Un clic sur un match ouvre les statistiques de tous ses joueurs et ses événements."
        )
        if len(self.rows) == 0:
            hint = T("Cette session ne contient encore aucun match enregistré.")
        self.hint = QLabel(
            T(
                "{hint}\n"
                "— : donnée non reçue ; 0 : valeur reçue égale à zéro.\n"
                "Les statistiques peuvent être partielles ; les événements "
                "couvrent seulement la période de connexion. Cette fenêtre est un "
                "instantané à son ouverture.",
                hint=hint,
            )
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button = close.button(QDialogButtonBox.StandardButton.Close)
        set_text(button, "text", T("Fermer"), button.setText)
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
