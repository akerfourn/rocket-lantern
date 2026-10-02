"""Normalize the two observed Stats API representations of the Data field."""

import json


def normalize_message(message: object) -> object:
    """Decode string-encoded Data once, leaving object payloads unchanged."""
    if not isinstance(message, dict):
        return message
    data = message.get("Data")
    if not isinstance(data, str):
        return message
    try:
        decoded = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Data contient du JSON invalide : ligne {error.lineno}, colonne {error.colno}."
        ) from None
    except (ValueError, RecursionError):
        raise ValueError("Data contient du JSON invalide ou trop imbriqué.") from None
    if not isinstance(decoded, dict):
        raise ValueError("Data encodé en chaîne doit contenir un objet JSON.")
    return {**message, "Data": decoded}
