"""Regression coverage for the string-encoded Data observed from the game."""

import json

import pytest

from rocket_lantern.protocol import normalize_message


def test_protocol_should_decode_data_when_game_sends_json_inside_string() -> None:
    data = {"MatchGuid": "synthetic-match", "Players": [], "Game": {"PlaylistId": 11}}
    message = {"Event": "UpdateState", "Data": json.dumps(data)}

    normalized = normalize_message(message)

    assert normalized == {"Event": "UpdateState", "Data": data}
    assert isinstance(message["Data"], str), "Decoding must not mutate the original envelope"


def test_protocol_should_preserve_message_when_data_is_already_an_object() -> None:
    message = {"Event": "MatchEnded", "Data": {"WinnerTeamNum": 0}}

    assert normalize_message(message) == message


def test_protocol_should_raise_safe_error_when_encoded_data_is_invalid() -> None:
    message = {"Event": "UpdateState", "Data": '{"Name":"Private Player",'}

    with pytest.raises(
        ValueError, match="Data contient du JSON invalide : ligne 1, colonne"
    ) as error:
        normalize_message(message)

    assert "Private Player" not in str(error.value)


@pytest.mark.parametrize("encoded_data", ["null", "[]", '"Private Player"'])
def test_protocol_should_reject_non_object_when_string_decodes_to_wrong_type(
    encoded_data: str,
) -> None:
    with pytest.raises(ValueError, match="Data encodé en chaîne doit contenir un objet JSON"):
        normalize_message({"Event": "UpdateState", "Data": encoded_data})
