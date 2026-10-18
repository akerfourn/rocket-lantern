"""Teammate-only telemetry, opt-in consent and independent HUD lifecycle."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.boost_overlay import BoostOverlay
from rocket_lantern.i18n import language_manager
from rocket_lantern.overlay_placement import parse_placement
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow

OBSERVED_AT = "2026-10-18T18:00:00+00:00"


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.live.set_player("me")
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


@pytest.fixture
def consent(monkeypatch: pytest.MonkeyPatch) -> Mock:
    warning = Mock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    return warning


def observe(
    window: MainWindow, boost: object = 65, guid: str = "live", *, playlist: int | None = None
) -> None:
    window.live.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": guid,
                "Game": {"PlaylistId": playlist},
                "Players": [
                    {"PrimaryId": "me", "Name": "Same", "TeamNum": 0, "Boost": 90},
                    {"PrimaryId": "mate", "Name": "Same", "TeamNum": 0, "Boost": boost},
                    {"PrimaryId": "enemy", "Name": "Other", "TeamNum": 1, "Boost": 100},
                ],
            },
        },
        OBSERVED_AT,
        False,
    )


def enable(window: MainWindow) -> BoostOverlay:
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    hud = window.boost_overlay.window
    assert isinstance(hud, BoostOverlay)
    return hud


@pytest.mark.parametrize("playlist", [6, 24, 73, 9])
def test_private_scope_should_show_teammates_in_private_lan_and_free_play(
    window: MainWindow, consent: Mock, playlist: int
) -> None:
    observe(window, playlist=playlist)

    window.settings.boost_overlay.scope.setCurrentIndex(1)

    assert window.boost_overlay.window.isVisible()
    assert set(window.boost_overlay.window.gauges) == {"mate"}
    assert window.store.setting("boost_overlay_mode") == "private"


@pytest.mark.parametrize("playlist", [None, 2, 11, 22, 34, 999])
def test_private_scope_should_not_allocate_a_hud_for_public_or_unknown_matches(
    window: MainWindow, consent: Mock, playlist: int | None
) -> None:
    observe(window, playlist=playlist)

    window.settings.boost_overlay.scope.setCurrentIndex(1)

    assert window.boost_overlay.window is None
    assert window.settings.boost_overlay.scope.currentData() == "private"


def test_private_scope_should_hide_on_mode_changes_without_erasing_the_preference(
    window: MainWindow, consent: Mock
) -> None:
    observe(window, playlist=6)
    window.settings.boost_overlay.scope.setCurrentIndex(1)
    hud = window.boost_overlay.window
    assert hud.isVisible()

    # Even consecutive packets with the same GUID must not retain a private mode.
    for playlist in (2, 11, None, 999):
        observe(window, playlist=playlist)
        assert not hud.isVisible()
        assert window.store.setting("boost_overlay_mode") == "private"

    observe(window, playlist=73)
    assert hud.isVisible()
    consent.assert_called_once()


def test_scope_change_should_take_effect_immediately_in_a_public_match(
    window: MainWindow, consent: Mock
) -> None:
    observe(window, playlist=11)
    controls = window.settings.boost_overlay
    controls.scope.setCurrentIndex(1)
    assert window.boost_overlay.window is None

    controls.scope.setCurrentIndex(2)
    hud = window.boost_overlay.window
    assert hud.isVisible()
    assert window.store.setting("boost_overlay_mode") == "all"

    controls.scope.setCurrentIndex(1)
    assert not hud.isVisible()
    assert window.store.setting("boost_overlay_mode") == "private"

    controls.scope.setCurrentIndex(0)
    observe(window, playlist=6)
    assert not hud.isVisible()
    assert window.store.setting("boost_overlay_mode") == "never"
    consent.assert_called_once()


def test_boost_should_stay_disabled_and_not_allocate_a_hud_before_explicit_consent(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)

    assert not window.settings.boost_overlay.activation_enabled()
    assert window.settings.boost_overlay.scope.currentData() == "never"
    assert [window.settings.boost_overlay.scope.itemText(index) for index in range(3)] == [
        "Jamais",
        "Parties privées uniquement",
        "Toutes les parties",
    ]
    assert window.boost_overlay.window is None
    consent.assert_not_called()


def test_boost_should_cancel_activation_without_enabling_or_allocating_a_hud(
    window: MainWindow, consent: Mock
) -> None:
    consent.return_value = QMessageBox.StandardButton.Cancel
    observe(window)

    window.settings.boost_overlay.scope.setCurrentIndex(2)

    assert not window.settings.boost_overlay.activation_enabled()
    assert window.boost_overlay.window is None
    assert consent.call_args.args[-1] == QMessageBox.StandardButton.Cancel
    assert "bannissement" in consent.call_args.args[2]


def test_boost_should_show_only_teammates_and_reuse_their_gauges(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)
    gauge = hud.gauges["mate"]

    assert set(hud.gauges) == {"mate"}, "IDs, not identical names, determine teammates"
    assert gauge.bar.value() == 65
    assert "#23834a" in gauge.bar.styleSheet()
    assert hud.isVisible()
    assert not window.settings.overlay.enabled.isChecked()
    assert hud.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert hud.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert hud.parent() is None
    observe(window, 40)
    assert hud.gauges["mate"] is gauge
    assert gauge.bar.value() == 40
    assert "#c87518" in gauge.bar.styleSheet()
    consent.assert_called_once()


def test_boost_should_not_open_reentrant_warnings_when_data_arrives_during_consent(
    window: MainWindow, consent: Mock
) -> None:
    def receive_during_warning(*args: object) -> QMessageBox.StandardButton:
        observe(window, 40)
        return QMessageBox.StandardButton.Yes

    consent.side_effect = receive_during_warning

    hud = enable(window)

    consent.assert_called_once()
    assert hud.isVisible()
    assert hud.gauges["mate"].bar.value() == 40
    assert window.settings.boost_overlay.activation_enabled()


def test_boost_should_accept_the_real_modal_confirmation_while_receiving_a_live_packet(
    window: MainWindow, application: QApplication
) -> None:
    def confirm_with_live_packet() -> None:
        observe(window, 20)
        dialog = application.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        dialog.button(QMessageBox.StandardButton.Yes).click()

    QTimer.singleShot(0, confirm_with_live_packet)

    hud = enable(window)

    assert hud.isVisible()
    assert hud.gauges["mate"].bar.value() == 20


def test_boost_should_not_restart_native_guard_on_every_telemetry_packet(
    window: MainWindow, consent: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = Mock()
    monkeypatch.setattr(window.boost_overlay, "_start_monitor", start)
    observe(window)
    enable(window)

    observe(window, 25)
    observe(window, 10)

    start.assert_called_once()


@pytest.mark.parametrize("boost", [0, None, "invalid", 101])
def test_boost_should_render_zero_or_unknown_without_inventing_received_values(
    window: MainWindow, consent: Mock, boost: object
) -> None:
    observe(window, boost)
    hud = enable(window)
    gauge = hud.gauges["mate"]

    if boost == 0:
        assert gauge.bar.maximum() == 0
        assert gauge.amount.text() == "0 % · vide"
        assert gauge.bar.animation.state() == QAbstractAnimation.State.Running
    else:
        assert not gauge.bar.isEnabled()
        assert gauge.amount.text() == "—"
    window.settings.boost_overlay.scope.setCurrentIndex(0)
    assert gauge.bar.animation.state() == QAbstractAnimation.State.Stopped


def test_boost_should_follow_player_selection_and_hide_when_no_teammate_is_identifiable(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)

    window.live.set_player("mate")
    assert set(hud.gauges) == {"me"}
    assert hud.gauges["me"].bar.value() == 90
    window.live.set_player("enemy")
    assert hud.gauges == {}
    assert not hud.isVisible()
    window.live.set_player("missing")
    assert not hud.isVisible()
    window.live.set_player("me")
    assert hud.isVisible()


@pytest.mark.parametrize(
    "event", ["MatchEnded", "PodiumStart", "GoalReplayStart", "MatchDestroyed"]
)
def test_boost_should_hide_on_match_end_departure_or_goal_replay(
    window: MainWindow, consent: Mock, event: str
) -> None:
    observe(window)
    hud = enable(window)

    window.live.observe({"Event": event, "Data": {"MatchGuid": "live"}}, OBSERVED_AT, False)

    assert not hud.isVisible()
    assert hud.gauges == {}


def test_boost_should_hide_on_disconnect_and_recover_on_next_valid_state(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)

    window._connection_lost()
    assert not hud.isVisible()
    assert hud.gauges == {}
    assert not window.boost_overlay._expiry.isActive()
    observe(window, 10, "new-game")
    assert hud.isVisible()
    assert hud.gauges["mate"].bar.value() == 10


def test_boost_should_mark_omitted_teammate_boost_but_not_a_missing_car_as_empty(
    window: MainWindow, consent: Mock
) -> None:
    message = {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "live",
            "Game": {},
            "Players": [
                {"PrimaryId": "me", "Name": "Me", "TeamNum": 0},
                {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0},
            ],
        },
    }
    window.live.observe(message, OBSERVED_AT, False)
    hud = enable(window)
    gauge = hud.gauges["mate"]
    assert gauge.amount.text() == "≈ 0 %"
    assert gauge.bar.maximum() == 0
    assert window.live.state.boost["mate"] is None

    message["Data"]["Players"][1]["bHasCar"] = False
    window.live.observe(message, OBSERVED_AT, False)
    assert gauge.amount.text() == "—"
    assert not gauge.bar.isEnabled()


def test_boost_should_hide_for_historical_replay_and_clear_previous_match_teammates(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)
    window.live.observe(
        {"Event": "UpdateState", "Data": {"MatchGuid": "replay", "Game": {}}},
        OBSERVED_AT,
        True,
    )
    assert not hud.isVisible()
    assert hud.gauges == {}
    observe(window)
    assert hud.isVisible()
    window.live.observe(
        {"Event": "MatchCreated", "Data": {"MatchGuid": "new-game"}},
        OBSERVED_AT,
        False,
    )
    assert not hud.isVisible()
    assert hud.gauges == {}


def test_boost_should_expire_stale_data_without_clock_events_renewing_freshness(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)
    assert window.boost_overlay._expiry.interval() == 3000

    window.boost_overlay._expiry.timeout.emit()
    assert not hud.isVisible()
    window.live.observe(
        {"Event": "ClockUpdatedSeconds", "Data": {"MatchGuid": "live", "TimeSeconds": 100}},
        OBSERVED_AT,
        False,
    )
    assert not hud.isVisible(), "A clock event must not make old boost look current"
    observe(window, 30)
    assert hud.isVisible()


def test_boost_should_save_separate_placement_without_enabling_or_requesting_consent(
    window: MainWindow, consent: Mock
) -> None:
    window.settings.boost_overlay.place_button.click()
    editor = window.boost_overlay.editor
    assert editor is not None
    assert set(editor.preview.display.gauges) == {"preview-1", "preview-2"}
    editor.preview.place(QPoint(130, 170))

    editor.save_button.click()

    assert window.boost_overlay.window is None
    assert window.store.setting("overlay_placement") == ""
    saved = parse_placement(window.store.setting("boost_overlay_placement"))
    assert saved.x_ratio is not None
    assert not window.settings.boost_overlay.activation_enabled()
    consent.assert_not_called()
    reopened = MainWindow(window.store)
    try:
        assert reopened.boost_overlay._placement == saved
        assert not reopened.settings.boost_overlay.activation_enabled()
        assert not reopened.boost_overlay._risk_accepted
    finally:
        reopened.close()


def test_boost_should_restore_live_hud_after_cancel_without_duplicate_consent(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)
    window.settings.boost_overlay.place_button.click()
    assert not hud.isVisible()

    window.boost_overlay.editor.cancel_button.click()

    assert hud.isVisible()
    assert window.store.setting("boost_overlay_placement") == ""
    consent.assert_called_once()


def test_boost_should_translate_controls_warning_and_live_labels_without_resetting_data(
    window: MainWindow, consent: Mock, application: QApplication
) -> None:
    observe(window, 0)
    hud = enable(window)
    language_manager().set_language("en")
    application.processEvents()

    assert window.settings.boost_overlay.scope.itemText(1) == "Private matches only"
    assert window.settings.boost_overlay.scope.itemText(0) == "Never"
    assert window.settings.boost_overlay.scope.itemText(2) == "All matches"
    assert "Risk of a ban" in window.settings.boost_overlay.warning.text()
    assert hud.gauges["mate"].amount.text() == "0 % · empty"
    assert hud.gauges["mate"].name.text() == "Same"
    assert "(test)" not in window.settings.overlay.enabled.text()


def test_boost_should_close_editor_hud_and_timer_without_restoring_windows_on_shutdown(
    window: MainWindow, consent: Mock
) -> None:
    observe(window)
    hud = enable(window)
    window.settings.boost_overlay.place_button.click()

    window.close()

    assert not hud.isVisible()
    assert window.boost_overlay.window is None
    assert window.boost_overlay.editor is None
    assert not window.boost_overlay._expiry.isActive()
