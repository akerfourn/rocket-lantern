"""Journal visibility, privacy and bounded retention contracts."""

import json
from datetime import UTC, datetime

import pytest
from PySide6.QtWidgets import QApplication

from rl_winloose.log_panel import MAX_LOG_ENTRIES, LogPanel

OBSERVED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("encode_data", [False, True])
def test_logs_should_redact_nested_identities_when_message_contains_players(
    application: QApplication,
    encode_data: bool,
) -> None:
    panel = LogPanel()
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
    assert "entry-1009" in text


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
