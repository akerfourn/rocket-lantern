"""Live player groups and team totals, without replacing missing counters with zero."""

from collections.abc import Mapping, Sequence
from dataclasses import astuple, dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.player_encounter_icons import ICON_HEIGHT, ICON_WIDTH, player_encounter_icon
from rocket_lantern.player_encounters import EncounterScope
from rocket_lantern.stat_header import StatHeader
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import tooltip

TEAM_ROLE = Qt.ItemDataRole.UserRole + 1
ENCOUNTER_ROLE = Qt.ItemDataRole.UserRole + 2
TEAM_COLORS = {0: "#56b4e9", 1: "#e69f00"}
LIVE_STAT_LABELS = {
    "score": STAT_LABELS["score"],
    "goals": STAT_LABELS["goals"],
    "assists": STAT_LABELS["assists"],
    "saves": STAT_LABELS["saves"],
    "posts": "Poteaux adverses",
    "shots": STAT_LABELS["shots"],
    "touches": STAT_LABELS["touches"],
    "demos": STAT_LABELS["demos"],
    "car_touches": STAT_LABELS["car_touches"],
}


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


def saves_display(value: str, epic_saves: int) -> str:
    """Keep the received total unchanged; epic saves are a subset, not extra saves."""
    if epic_saves > 0:
        return f"{value} ({epic_saves})"
    return value


class LiveTeamTable(QTableWidget):
    """Combine each team's heading and totals in one row to keep trios compact."""

    def __init__(self) -> None:
        super().__init__(0, 1 + len(LIVE_STAT_LABELS))
        self._signature: tuple[object, ...] | None = None
        self._player_id = ""
        self._encounters: dict[str, EncounterScope] = {}
        self._player_icons: dict[tuple[int, EncounterScope | None], QIcon] = {}
        self._team_icons = {}
        for team, color in TEAM_COLORS.items():
            stripe = QPixmap(6, 32)
            stripe.setDevicePixelRatio(2)
            stripe.fill(QColor(color))
            self._team_icons[team] = QIcon(stripe)
            for scope in (None, *EncounterScope):
                self._player_icons[team, scope] = player_encounter_icon(color, scope)
        self.setIconSize(QSize(ICON_WIDTH, ICON_HEIGHT))
        self._configure_headers()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setMaximumSectionSize(240)
        tooltip(self, T("— : donnée absente ; 0 : zéro reçu. Le joueur suivi est en gras."))

    def _configure_headers(self) -> None:
        self.setHorizontalHeader(StatHeader(self))
        self.setHorizontalHeaderLabels([T("Joueur"), *[""] * len(LIVE_STAT_LABELS)])
        for column, (field, label) in enumerate(LIVE_STAT_LABELS.items(), start=1):
            item = self.horizontalHeaderItem(column)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setToolTip(T(label))
            item.setData(Qt.ItemDataRole.AccessibleTextRole, T(label))
            if field == "saves":
                item.setToolTip(T("Arrêts · entre parenthèses : arrêts miraculeux observés."))
            elif field == "posts":
                item.setToolTip(
                    T("Poteaux et transversale adverses touchés · événements observés.")
                )
            item.setIcon(QIcon(str(ASSET_DIRECTORY / f"stat-{field}.svg")))

    def clear_players(self) -> None:
        self.clearSpans()
        self.setRowCount(0)
        self._signature = None
        self._encounters.clear()

    def set_encounters(self, encounters: Mapping[str, EncounterScope]) -> None:
        """Refresh name decorations in place without rebuilding scores or player rows."""
        if self._encounters == encounters:
            return
        self._encounters = dict(encounters)
        for row in range(self.rowCount()):
            name = self.item(row, 0)
            if name is not None and isinstance(name.data(Qt.ItemDataRole.UserRole), str):
                self._decorate_player(name, name.data(TEAM_ROLE))

    def _decorate_player(self, name: QTableWidgetItem, team: int) -> None:
        primary_id = name.data(Qt.ItemDataRole.UserRole)
        scope = None
        if primary_id != self._player_id:
            scope = self._encounters.get(primary_id)
        description: DisplayText = name.text()
        if scope == EncounterScope.SESSION:
            description = T("{name}\nDéjà croisé dans la session actuelle.", name=name.text())
        elif scope == EncounterScope.HISTORY:
            description = T("{name}\nDéjà croisé dans l’historique.", name=name.text())
        name.setIcon(self._player_icons[team, scope])
        name.setData(ENCOUNTER_ROLE, scope)
        name.setToolTip(description)
        name.setData(Qt.ItemDataRole.AccessibleTextRole, description)

    def update_players(
        self,
        players: Sequence[PlayerStats],
        player_id: str,
        epic_saves: Mapping[str, int] | None = None,
        *,
        opponent_post_hits: Mapping[str, int] | None = None,
        show_team_totals: bool = True,
    ) -> bool:
        """Return whether visible rows changed, allowing overlays to resize only when needed."""
        if epic_saves is None:
            epic_saves = {}
        if opponent_post_hits is None:
            opponent_post_hits = {}
        self._player_id = player_id
        signature = (
            player_id,
            show_team_totals,
            tuple(
                (
                    astuple(player),
                    epic_saves.get(player.primary_id, 0),
                    opponent_post_hits.get(player.primary_id, 0),
                )
                for player in sorted(players, key=lambda player: player.primary_id)
            ),
        )
        if self._signature == signature:
            return False
        self._signature = signature
        selected_team = None
        groups: dict[int, list[PlayerStats]] = {}
        for player in players:
            groups.setdefault(player.team, []).append(player)
            if player.primary_id == player_id:
                selected_team = player.team
        teams = sorted(groups, key=lambda team: (team != selected_team, team))
        self.clearSpans()
        headings = len(teams) if show_team_totals else 0
        self.setRowCount(len(players) + headings + max(0, len(teams) - 1))
        row = 0
        for index, team in enumerate(teams):
            if index > 0:
                self._render_separator(row)
                row += 1
            members = sorted(groups[team], key=player_order)
            team_epic_saves = sum(epic_saves.get(player.primary_id, 0) for player in members)
            team_post_hits = sum(opponent_post_hits.get(player.primary_id, 0) for player in members)
            if show_team_totals:
                self._render_team(
                    row,
                    team,
                    members,
                    epic_saves=team_epic_saves,
                    opponent_post_hits=team_post_hits,
                )
                row += 1
            for member_index, player in enumerate(members):
                self._render_player(
                    row,
                    player,
                    player_id,
                    member_index,
                    epic_saves=epic_saves.get(player.primary_id, 0),
                    opponent_post_hits=opponent_post_hits.get(player.primary_id, 0),
                )
                row += 1
        return True

    def _render_separator(self, row: int) -> None:
        for column in range(self.columnCount()):
            spacer = QTableWidgetItem("")
            spacer.setFlags(Qt.ItemFlag.NoItemFlags)
            spacer.setBackground(self.palette().base())
            self.setItem(row, column, spacer)
        self.setSpan(row, 0, 1, self.columnCount())
        self.setRowHeight(row, 10)

    def _render_team(
        self,
        row: int,
        team: int,
        players: Sequence[PlayerStats],
        *,
        epic_saves: int,
        opponent_post_hits: int,
    ) -> None:
        self.setRowHeight(row, self.verticalHeader().defaultSectionSize())
        title = {0: T("Équipe bleue"), 1: T("Équipe orange")}[team]
        heading = QTableWidgetItem(title)
        heading.setToolTip(T("Total des joueurs présents"))
        totals = team_totals(players)
        totals["posts"] = TeamTotal(opponent_post_hits, len(players), len(players))
        items = [heading]
        for field in LIVE_STAT_LABELS:
            total = totals[field]
            text = total.display()
            if field == "saves":
                text = saves_display(text, epic_saves)
            item = QTableWidgetItem(text)
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

    def _render_player(
        self,
        row: int,
        player: PlayerStats,
        player_id: str,
        index: int,
        *,
        epic_saves: int,
        opponent_post_hits: int,
    ) -> None:
        self.setRowHeight(row, self.verticalHeader().defaultSectionSize())
        name = QTableWidgetItem(player.name)
        name.setData(Qt.ItemDataRole.UserRole, player.primary_id)
        self._decorate_player(name, player.team)
        items = [name]
        for field in LIVE_STAT_LABELS:
            if field == "posts":
                value = opponent_post_hits
            else:
                value = getattr(player, field)
            text = "—"
            if value is not None:
                text = str(value)
            if field == "saves":
                text = saves_display(text, epic_saves)
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
