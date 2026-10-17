"""Optional first-run setup uses explicit actions and the normal SQLite preferences."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.game_installations_panel import ConfigurationCheck
from rocket_lantern.i18n import language_manager
from rocket_lantern.installation_preferences import CACHE_KEY, ONBOARDING_KEY
from rocket_lantern.packet_configuration import read_configuration
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    language_manager().set_language("fr")
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    application.processEvents()
    yield widget
    if widget.onboarding.dialog is not None:
        widget.onboarding.dialog.reject()
    widget.close()
    store.close()
    language_manager().set_language("fr")


def test_onboarding_should_offer_setup_only_once_without_automatic_discovery(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = Mock(spec=QThreadPool)
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )
    detector = Mock()
    window.settings.game_installations.detector = detector
    assert window.onboarding.dialog is None

    window.offer_onboarding()
    dialog = window.onboarding.dialog
    assert dialog is not None
    dialog.installations.detector = detector
    window.offer_onboarding()

    assert window.onboarding.dialog is dialog
    assert dialog.isVisible()
    assert dialog.installations.rows == []
    assert dialog.installations.packet_rate.value() == 10
    detector.assert_not_called()
    pool.start.assert_not_called()


@pytest.mark.parametrize("action", ["skip", "finish", "close"])
def test_onboarding_should_remember_user_choice_and_allow_manual_reopening(
    window: MainWindow,
    action: str,
) -> None:
    window.offer_onboarding()
    dialog = window.onboarding.dialog
    if action == "finish":
        dialog.finish_button.click()
    elif action == "skip":
        dialog.skip_button.click()
    else:
        dialog.close()

    expected = "completed" if action == "finish" else "skipped"
    assert window.store.setting(ONBOARDING_KEY) == expected
    assert window.onboarding.dialog is None
    reopened = MainWindow(window.store)
    try:
        reopened.offer_onboarding()
        assert reopened.onboarding.dialog is None
        reopened.settings.onboarding_button.click()
        assert reopened.onboarding.dialog is not None
        reopened.onboarding.dialog.reject()
    finally:
        reopened.close()


def test_onboarding_should_sync_port_language_and_rate_without_editing_game_files(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.offer_onboarding()
    dialog = window.onboarding.dialog
    detector = Mock()
    dialog.installations.detector = detector

    dialog.port.setValue(49125)
    dialog.installations.packet_rate.setValue(20)
    dialog.language.setCurrentIndex(dialog.language.findData("en"))
    application.processEvents()

    assert window.store.setting("port") == "49125"
    assert window.store.setting("packet_send_rate") == "20"
    assert window.store.setting("language") == "en"
    assert window.settings.game_installations.packet_rate.value() == 20
    assert dialog.windowTitle() == "Welcome to RocketLantern"
    assert dialog.finish_button.text() == "Finish"
    detector.assert_not_called()


def test_onboarding_should_reconnect_changed_port_only_when_user_finishes(
    window: MainWindow,
) -> None:
    window.client.start = Mock()
    window.offer_onboarding()
    dialog = window.onboarding.dialog
    dialog.port.setValue(49125)
    window.client.start.assert_not_called()

    dialog.finish_button.click()

    window.client.start.assert_called_once_with(49125)


def test_onboarding_should_sync_language_selector_when_catalog_changes_directly(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.offer_onboarding()

    language_manager().set_language("en")
    application.processEvents()

    assert window.onboarding.dialog.language.currentData() == "en"
    assert window.onboarding.dialog.finish_button.text() == "Finish"


def test_onboarding_should_save_discovery_and_require_fresh_check_after_restart(
    window: MainWindow,
    tmp_path: Path,
) -> None:
    path = tmp_path / "RocketLeague/TAGame/Config/DefaultStatsAPI.ini"
    path.parent.mkdir(parents=True)
    path.write_text("[TAGame.MatchStatsExporter_TA]\nPacketSendRate=1\n", encoding="utf-8")
    installation = GameInstallation("Steam", path.parents[2], path)
    checked = read_configuration(installation)
    original = path.read_bytes()
    window.offer_onboarding()
    dialog = window.onboarding.dialog

    dialog.installations._completed(
        ConfigurationCheck(DiscoveryReport((installation,)), (checked,))
    )

    assert dialog.installations.rows[0].apply_button.isEnabled()
    assert json.loads(window.store.setting(CACHE_KEY)) == [
        {"launcher": "Steam", "directory": str(installation.directory)},
    ]
    assert window.settings.game_installations.rows == []
    assert "à vérifier" in window.settings.game_installations.known_paths.text()
    dialog.skip_button.click()
    reopened = MainWindow(window.store)
    try:
        panel = reopened.settings.game_installations
        assert panel.rows == [], "Remembered paths must never enable an unchecked INI write"
        assert str(installation.directory) in panel.known_paths.text()
        assert path.read_bytes() == original
    finally:
        reopened.close()


def test_onboarding_should_apply_only_after_explicit_click_and_preserve_backup(
    window: MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "RocketLeague/TAGame/Config/DefaultStatsAPI.ini"
    path.parent.mkdir(parents=True)
    path.write_text("[TAGame.MatchStatsExporter_TA]\nPacketSendRate=0\n", encoding="utf-8")
    installation = GameInstallation("Epic Games", path.parents[2], path)
    checked = read_configuration(installation)
    original = path.read_bytes()
    window.offer_onboarding()
    dialog = window.onboarding.dialog
    panel = dialog.installations
    panel.detector = Mock(return_value=DiscoveryReport((installation,)))
    pool = Mock(spec=QThreadPool)
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )

    panel.detect_button.click()
    assert panel.is_busy
    assert not dialog.skip_button.isEnabled()
    dialog.reject()
    assert window.onboarding.dialog is dialog
    assert path.read_bytes() == original
    pool.start.call_args.args[0].run()
    assert panel.rows[0].configuration == checked
    assert path.read_bytes() == original

    panel.rows[0].apply_button.click()
    assert panel.is_busy
    pool.start.call_args.args[0].run()

    assert not panel.is_busy
    assert read_configuration(installation).rate == 10
    assert path.with_name(path.name + ".rocketlantern.bak").read_bytes() == original
    assert dialog.finish_button.isEnabled()


def test_onboarding_should_report_persistence_failure_without_blocking_the_app(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window.offer_onboarding()
    failed = Mock(side_effect=sqlite3.OperationalError("synthetic failure"))
    monkeypatch.setattr(window.store, "set_setting", failed)

    window.onboarding.dialog.skip_button.click()

    assert window.onboarding.dialog is None
    assert "Erreur SQLite" in window.notice.text()


def test_onboarding_should_ignore_late_worker_results_after_application_shutdown(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window.offer_onboarding()
    dialog = window.onboarding.dialog
    window.close()
    save = Mock(side_effect=AssertionError("No database writes after shutdown"))
    monkeypatch.setattr(window.store, "set_setting", save)

    dialog.installations._completed(ConfigurationCheck(DiscoveryReport(), ()))
    dialog.reject()

    assert not dialog.isVisible()
    save.assert_not_called()
