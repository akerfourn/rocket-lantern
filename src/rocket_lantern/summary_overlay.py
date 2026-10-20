"""Small, non-interactive desktop overlay; never hook or inject into the game."""

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from rocket_lantern.i18n import DisplayText, render
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.label_icons import label_icon
from rocket_lantern.labels import DEFAULT_LIST, LabelList
from rocket_lantern.result_summary import balance_icon, outcome_icon
from rocket_lantern.storage import Summary
from rocket_lantern.summary_overlay_content import SummaryOverlayContent
from rocket_lantern.translated_widgets import binding, set_text, tooltip


def overlay_position(bounds: QRect, size: QSize, corner: str, margin: int = 20) -> QPoint:
    """Place a compact HUD inside a screen, including monitors with negative coordinates."""
    left = bounds.left() + margin
    top = bounds.top() + margin
    right = bounds.left() + bounds.width() - size.width() - margin
    bottom = bounds.top() + bounds.height() - size.height() - margin
    x = left
    y = top
    if corner in ("top_right", "bottom_right"):
        x = right
    if corner in ("bottom_left", "bottom_right"):
        y = bottom
    x = max(bounds.left(), min(x, bounds.left() + max(0, bounds.width() - size.width())))
    y = max(bounds.top(), min(y, bounds.top() + max(0, bounds.height() - size.height())))
    return QPoint(x, y)


class OverlayDisplay(QWidget):
    """Shared translucent background for the desktop HUDs and placement previews."""

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 18, 24, 215))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 8, 8)
        finally:
            painter.end()


def configure_overlay(window: QWidget) -> None:
    """Do not steal focus or mouse input from the game, even while being shown."""
    window.setWindowFlags(
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowTransparentForInput
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    window.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
    window.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class SummaryDisplay(OverlayDisplay):
    """Shared compact rendering for the click-through HUD and its interactive preview."""

    def __init__(
        self, parent: QWidget | None = None, flags: Qt.WindowType = Qt.WindowType.Widget
    ) -> None:
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("QLabel { color: #f3f4f6; font-size: 22px; font-weight: 600; }")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(12, 8, 12, 8)
        self._row.setSpacing(16)
        self.wins_group, self.wins_symbol, self.wins = self._add_counter(
            outcome_icon("win").pixmap(22, 22)
        )
        self.losses_group, self.losses_symbol, self.losses = self._add_counter(
            outcome_icon("loss").pixmap(22, 22)
        )
        self._balance_icons = {value: balance_icon(value) for value in (-1, 0, 1)}
        self.delta_group, self.balance_symbol, self.balance = self._add_counter(
            self._balance_icons[0].pixmap(22, 22)
        )
        self.content = SummaryOverlayContent()
        self.label_symbols: dict[str, QLabel] = {}
        self._label_titles: dict[str, DisplayText] = {}
        self._summary = Summary(0, 0, 0)
        binding(self).callbacks.append(self._update_accessibility)
        self.set_summary(self._summary)

    def _add_counter(self, pixmap: QPixmap) -> tuple[QWidget, QLabel, QLabel]:
        group = QWidget(self)
        group.setMinimumHeight(28)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        symbol = QLabel()
        symbol.setFixedSize(22, 22)
        symbol.setPixmap(pixmap)
        layout.addWidget(symbol)
        count = QLabel()
        layout.addWidget(count)
        self._row.addWidget(group)
        return group, symbol, count

    def set_content(
        self, content: SummaryOverlayContent, catalog: LabelCatalog, choices: dict[str, str]
    ) -> None:
        self.content = content
        self.wins_group.setVisible(content.wins)
        self.losses_group.setVisible(content.losses)
        self.delta_group.setVisible(content.delta)
        categories = [item for item in catalog.enabled_lists() if item.id in content.label_lists]
        active = {item.id for item in categories}
        for key in tuple(self.label_symbols):
            if key not in active:
                symbol = self.label_symbols.pop(key)
                self._row.removeWidget(symbol)
                symbol.hide()
                symbol.deleteLater()
        self._label_titles.clear()
        for category in categories:
            self._update_category(category, catalog, choices)
        self._update_accessibility()
        self._fit_content()

    def _update_category(
        self, category: LabelList, catalog: LabelCatalog, choices: dict[str, str]
    ) -> None:
        value = choices.get(category.id, "")
        if category.id == DEFAULT_LIST and value == "":
            value = "not_evaluated"
        definition = catalog.labels.get(value)
        title = T("Non évalué")
        if definition is not None and definition.list_id == category.id:
            title = definition.title
        else:
            definition = None
        description = T("{list_name} · {label}", list_name=category.title, label=title)
        self._label_titles[category.id] = description
        symbol = self.label_symbols.get(category.id)
        if symbol is None:
            symbol = QLabel(self)
            symbol.setFixedSize(28, 28)
            self.label_symbols[category.id] = symbol
        self._row.removeWidget(symbol)
        self._row.addWidget(symbol)
        symbol.setPixmap(label_icon(definition, category.family).pixmap(28, 28))
        tooltip(symbol, description)
        set_text(symbol, "accessibleName", description, symbol.setAccessibleName)
        symbol.show()

    def _fit_content(self) -> None:
        for group in (self.wins_group, self.losses_group, self.delta_group):
            group.layout().invalidate()
            group.layout().activate()
        self._row.invalidate()
        self._row.activate()
        self.adjustSize()

    def set_summary(self, summary: Summary) -> None:
        """Display the same persisted, filtered results as the application banner."""
        self._summary = summary
        balance = summary.wins - summary.losses
        direction = 0
        if balance > 0:
            direction = 1
        elif balance < 0:
            direction = -1
        self.wins.setText(str(summary.wins))
        self.losses.setText(str(summary.losses))
        self.balance.setText(f"{balance:+d}")
        self.balance_symbol.setPixmap(self._balance_icons[direction].pixmap(22, 22))
        self._update_accessibility()
        self._fit_content()

    def _update_accessibility(self) -> None:
        parts: list[str] = []
        balance = f"{self._summary.wins - self._summary.losses:+d}"
        if self.content.wins:
            parts.append(render(T("{wins} victoires", wins=self._summary.wins)))
        if self.content.losses:
            parts.append(render(T("{losses} défaites", losses=self._summary.losses)))
        if self.content.delta:
            parts.append(render(T("delta {balance}", balance=balance)))
        parts.extend(render(title) for title in self._label_titles.values())
        self.setAccessibleName(" · ".join(parts))


class SummaryOverlay(SummaryDisplay):
    """Unowned, click-through tool window independent of main-window minimization."""

    def __init__(self) -> None:
        super().__init__()
        configure_overlay(self)
        set_text(self, "windowTitle", T("RocketLantern · Overlay"), self.setWindowTitle)
