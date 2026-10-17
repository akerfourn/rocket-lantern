"""Journal visibility, privacy and bounded retention contracts."""

import json
from datetime import UTC, datetime

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern import log_panel
from rocket_lantern.log_panel import MAX_ENTRY_LENGTH, MAX_LOG_ENTRIES, LogPanel

OBSERVED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("encode_data", [False, True])
def test_logs_should_redact_nested_identities_when_message_contains_players(
    application: QApplication,
    encode_data: bool,
) -> None:
    panel = LogPanel()
    panel.api_details.setChecked(True)
    payload = {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "private-match-id",
            "Players": [{"Name": "Private Player", "PrimaryId": "Epic|secret|0", "TeamNum": 1}],
            "Game": {"PlaylistId": 11},
        },
    }

    wire_message = dict(payload)
    if encode_data:
        wire_message["Data"] = json.dumps(payload["Data"])
    decoded = panel.record_payload(json.dumps(wire_message), OBSERVED_AT)

    text = panel.text.toPlainText()
    assert "Private Player" not in text
    assert "Epic|secret|0" not in text
    assert "private-match-id" not in text
    assert '"TeamNum":1' in text
    assert '"PlaylistId":11' in text
    assert decoded == payload, "Redaction must not alter the message passed to the tracker"


def test_logs_should_hide_opaque_data_when_inner_json_is_invalid(application: QApplication) -> None:
    panel = LogPanel()
    panel.api_details.setChecked(True)
    payload = json.dumps({"Event": "UpdateState", "Data": '{"Name":"Private Player",'})

    with pytest.raises(ValueError, match="Data contient du JSON invalide"):
        panel.record_payload(payload, OBSERVED_AT)

    text = panel.text.toPlainText()
    assert "Private Player" not in text
    assert "Data non objet masqué" in text
    assert '"Event":"UpdateState"' in text


def test_logs_should_drop_old_entries_when_retention_limit_is_reached(
    application: QApplication,
) -> None:
    panel = LogPanel()
    for index in range(MAX_LOG_ENTRIES + 10):
        panel.append_entry("Test", f"entry-{index:04d}", OBSERVED_AT)

    text = panel.text.toPlainText()
    assert panel.text.document().blockCount() == MAX_LOG_ENTRIES
    assert "entry-0000" not in text
    assert f"entry-{MAX_LOG_ENTRIES + 9:04d}" in text


@pytest.mark.parametrize("event", ["UpdateState", "ClockUpdatedSeconds", "StatfeedEvent"])
def test_logs_should_skip_repetitive_events_without_affecting_tracking_by_default(
    application: QApplication, monkeypatch: pytest.MonkeyPatch, event: str
) -> None:
    panel = LogPanel()
    message = {"Event": event, "Data": {"Players": [{"Name": "Private Player"}]}}

    def unexpected_redaction(value: object, depth: int = 0) -> object:
        pytest.fail("Default logging must not build redacted copies of API payloads")

    monkeypatch.setattr(log_panel, "redact", unexpected_redaction)
    decoded = panel.record_payload(json.dumps(message), OBSERVED_AT)

    assert decoded == message
    assert panel.received_count == 1
    assert "1 messages reçus" in panel.summary.text()
    assert panel.text.toPlainText() == ""


def test_logs_should_keep_concise_match_events_without_payloads_by_default(
    application: QApplication,
) -> None:
    panel = LogPanel()
    message = {"Event": "GoalScored", "Data": {"Name": "Private Player", "GoalSpeed": 75}}

    decoded = panel.record_payload(json.dumps(message), OBSERVED_AT)

    assert decoded == message
    assert panel.text.toPlainText().endswith("[Événement] GoalScored")
    assert "Private Player" not in panel.text.toPlainText()
    assert "GoalSpeed" not in panel.text.toPlainText()


def test_logs_should_report_invalid_envelopes_without_exposing_payloads_by_default(
    application: QApplication,
) -> None:
    panel = LogPanel()
    payload = json.dumps({"Event": "UpdateState", "Data": '{"Name":"Private Player",'})

    with pytest.raises(ValueError, match="Data contient du JSON invalide"):
        panel.record_payload(payload, OBSERVED_AT)

    assert "Structure de message invalide" in panel.text.toPlainText()
    assert "Private Player" not in panel.text.toPlainText()


def test_logs_should_stop_detailed_capture_when_user_disables_it(application: QApplication) -> None:
    panel = LogPanel()
    panel.api_details.setChecked(True)
    payload = '{"Event":"UpdateState","Data":{"Game":{"PlaylistId":11}}}'
    panel.record_payload(payload, OBSERVED_AT)
    assert '"PlaylistId":11' in panel.text.toPlainText()

    panel.api_details.setChecked(False)
    panel.clear()
    decoded = panel.record_payload(payload, OBSERVED_AT)

    assert decoded == json.loads(payload)
    assert panel.text.toPlainText() == ""
    assert panel.received_count == 2


def test_logs_should_truncate_detailed_payloads_when_entry_limit_is_exceeded(
    application: QApplication,
) -> None:
    panel = LogPanel()
    panel.api_details.setChecked(True)
    payload = json.dumps({"Event": "UpdateState", "Data": {"Value": "x" * MAX_ENTRY_LENGTH * 2}})

    panel.record_payload(payload, OBSERVED_AT)

    text = panel.text.toPlainText()
    assert "[contenu tronqué]" in text
    assert len(text) < MAX_ENTRY_LENGTH + 100


def test_logs_should_start_without_api_details_when_another_panel_enabled_them(
    application: QApplication,
) -> None:
    first = LogPanel()
    first.api_details.setChecked(True)

    second = LogPanel()

    assert not second.api_details.isChecked()


def test_logs_should_keep_message_count_when_user_clears_display(application: QApplication) -> None:
    panel = LogPanel()
    panel.record_payload('{"Event":"GoalScored","Data":{}}', OBSERVED_AT)

    panel.clear()

    assert panel.text.toPlainText() == ""
    assert panel.received_count == 1


def test_logs_should_explain_invalid_json_when_payload_has_trailing_control_character(
    application: QApplication,
) -> None:
    panel = LogPanel()
    payload = '{"Event":"MatchCreated","Data":{"Name":"Private Player"}}\x00'

    with pytest.raises(ValueError, match="Extra data.*position"):
        panel.record_payload(payload, OBSERVED_AT)

    text = panel.text.toPlainText()
    assert "fin U+0000" in text
    assert "Private Player" not in text
    assert panel.received_count == 1
