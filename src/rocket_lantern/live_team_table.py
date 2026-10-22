"""Live player groups and team totals, without replacing missing counters with zero."""

from collections.abc import Sequence
from dataclasses import astuple, dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView

from rocket_lantern.i18n import text as T
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import tooltip

TEAM_ROLE = Qt.ItemDataRole.UserRole + 1
TEAM_COLORS = {0: "#56b4e9", 1: "#e69f00"}


@dataclass(frozen=True)
class TeamTotal:
    """Sum received nonnegative counters and retain the number of missing contributors."""

    value: int | None
    known_players: int
    player_count: int

    def display(self) -> str:
        if self.value is None:
            return "—"
        if self.known_players < self.player_count:
            return f"≥ {self.value}"
        return str(self.value)


def team_totals(players: Sequence[PlayerStats]) -> dict[str, TeamTotal]:
    """Aggregate only the currently visible players, never a previous match or snapshot."""
    totals = {}
    for field in STAT_LABELS:
        values = []
        for player in players:
            value: int | None = getattr(player, field)
            if value is not None:
                values.append(value)
        total = None
        if values:
            total = sum(values)
        totals[field] = TeamTotal(total, len(values), len(players))
    return totals


def player_order(player: PlayerStats) -> tuple[bool, int, str, str]:
    score = player.score
    if score is None:
        score = 0
    return player.score is None, -score, player.name.casefold(), player.primary_id


class LiveTeamTable(QTableWidget):
    """Combine each team's heading and totals in one row to keep trios compact."""

    def __init__(self) -> None:
        super().__init__(0, 1 + len(STAT_LABELS))
        self._signature: tuple[object, ...] | None = None
        self._team_icons = {}
        for team, color in TEAM_COLORS.items():
            stripe = QPixmap(6, 32)
            stripe.setDevicePixelRatio(2)
            stripe.fill(QColor(color))
            self._team_icons[team] = QIcon(stripe)
        self.setHorizontalHeaderLabels([T("Joueur"), *[T(value) for value in STAT_LABELS.values()]])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setMaximumSectionSize(240)
        tooltip(self, T("— : donnée absente ; 0 : zéro reçu. Le joueur suivi est en gras."))

    def clear_players(self) -> None:
        self.clearSpans()
        self.setRowCount(0)
        self._signature = None

    def update_players(self, players: Sequence[PlayerStats], player_id: str) -> None:
        signature = (
            player_id,
            tuple(
                astuple(player) for player in sorted(players, key=lambda player: player.primary_id)
            ),
        )
        if self._signature == signature:
            return
        self._signature = signature
        selected_team = None
        groups: dict[int, list[PlayerStats]] = {}
        for player in players:
            groups.setdefault(player.team, []).append(player)
            if player.primary_id == player_id:
                selected_team = player.team
        teams = sorted(groups, key=lambda team: (team != selected_team, team))
        self.clearSpans()
        self.setRowCount(len(players) + len(teams) + max(0, len(teams) - 1))
        row = 0
        for index, team in enumerate(teams):
            if index > 0:
                self._render_separator(row)
                row += 1
            members = sorted(groups[team], key=player_order)
            self._render_team(row, team, members)
            row += 1
            for member_index, player in enumerate(members):
                self._render_player(row, player, player_id, member_index)
                row += 1

    def _render_separator(self, row: int) -> None:
        for column in range(self.columnCount()):
            spacer = QTableWidgetItem("")
            spacer.setFlags(Qt.ItemFlag.NoItemFlags)
            spacer.setBackground(self.palette().base())
            self.setItem(row, column, spacer)
        self.setSpan(row, 0, 1, self.columnCount())
        self.setRowHeight(row, 10)

    def _render_team(self, row: int, team: int, players: Sequence[PlayerStats]) -> None:
        self.setRowHeight(row, self.verticalHeader().defaultSectionSize())
        title = {0: T("Équipe bleue"), 1: T("Équipe orange")}[team]
        heading = QTableWidgetItem(title)
        heading.setToolTip(T("Total des joueurs présents"))
        totals = team_totals(players)
        items = [heading]
        for total in totals.values():
            item = QTableWidgetItem(total.display())
            description = T("Total des joueurs présents")
            if total.value is None:
                description = T("Aucune valeur reçue.")
            elif total.known_players < total.player_count:
                description = T(
                    "Total partiel · valeurs reçues : {known}/{count}.",
                    known=total.known_players,
                    count=total.player_count,
                )
            item.setToolTip(description)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            items.append(item)
        background = QColor(TEAM_COLORS[team])
        background.setAlpha(55)
        font = QFont(self.font())
        font.setBold(True)
        for column, item in enumerate(items):
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(TEAM_ROLE, team)
            item.setFont(font)
            item.setBackground(background)
            self.setItem(row, column, item)
        heading.setForeground(QColor(TEAM_COLORS[team]))
        heading.setIcon(self._team_icons[team])

    def _render_player(self, row: int, player: PlayerStats, player_id: str, index: int) -> None:
        self.setRowHeight(row, self.verticalHeader().defaultSectionSize())
        name = QTableWidgetItem(player.name)
        name.setData(Qt.ItemDataRole.UserRole, player.primary_id)
        name.setIcon(self._team_icons[player.team])
        name.setToolTip(player.name)
        items = [name]
        for field in STAT_LABELS:
            value = getattr(player, field)
            text = "—"
            if value is not None:
                text = str(value)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            items.append(item)
        background = QColor(TEAM_COLORS[player.team])
        background.setAlpha(12 + (index % 2) * 10)
        font = QFont(self.font())
        font.setBold(player.primary_id == player_id)
        for column, item in enumerate(items):
            item.setData(TEAM_ROLE, player.team)
            item.setFont(font)
            item.setBackground(background)
            self.setItem(row, column, item)
