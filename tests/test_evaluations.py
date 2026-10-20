"""Assessments are per match, survive updates and never create a W/L result."""

import sqlite3
from pathlib import Path

import pytest

from rocket_lantern.evaluations import Evaluation
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult

TIMESTAMP = "2026-10-11T12:00:00+00:00"


def test_evaluation_should_default_to_unreviewed_without_modifying_history() -> None:
    store = MatchStore(":memory:")
    try:
        assert store.evaluation("missing") == Evaluation.NOT_EVALUATED
        assert store.connection.execute("SELECT COUNT(*) FROM match_details").fetchone()[0] == 0
    finally:
        store.close()


def test_evaluation_should_survive_result_updates_restarts_and_player_selection(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.sqlite3"
    store = MatchStore(path)
    try:
        store.set_evaluation("game", Evaluation.POSSIBLE, TIMESTAMP)
        assert store.summary("player").unknown == 0
        assert store.filtered_history("player", None, None) == []
        store.save(MatchResult("game", "player", TIMESTAMP, 11, "unknown"))
        store.save(MatchResult("game", "player", TIMESTAMP, 11, "win"))
        store.save(MatchResult("game", "mate", TIMESTAMP, 11, "loss"))
        assert store.filtered_history("player", None, None)[0]["evaluation"] == "possible"
        assert store.filtered_history("mate", None, None)[0]["evaluation"] == "possible"
        assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        store.close()
    reopened = MatchStore(path)
    try:
        assert reopened.evaluation("game") == Evaluation.POSSIBLE
        assert reopened.summary("player").wins == 1
        reopened.set_evaluation("game", Evaluation.STRONG, TIMESTAMP)
        reopened.set_evaluation("other", Evaluation.NO_SUSPICION, TIMESTAMP)
        reopened.set_evaluation("game", Evaluation.NOT_EVALUATED, TIMESTAMP)
        assert reopened.evaluation("game") == Evaluation.NOT_EVALUATED
        assert reopened.evaluation("other") == Evaluation.NO_SUSPICION
        assert reopened.connection.execute("SELECT COUNT(*) FROM match_labels").fetchone()[0] == 2
    finally:
        reopened.close()


@pytest.mark.parametrize("guid, value", [("", "possible"), ("game", "certain")])
def test_evaluation_should_reject_invalid_votes_without_writing(guid: str, value: str) -> None:
    store = MatchStore(":memory:")
    try:
        with pytest.raises(ValueError):
            store.set_evaluation(guid, value, TIMESTAMP)
        assert store.connection.execute("SELECT COUNT(*) FROM match_labels").fetchone()[0] == 0
    finally:
        store.close()


def test_evaluation_should_migrate_version_two_without_changing_results(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    store = MatchStore(path)
    store.save(MatchResult("game", "player", TIMESTAMP, 11, "win"))
    with store.connection:
        store.connection.execute("DROP TABLE match_labels")
        store.connection.execute("DROP TABLE labels")
        store.connection.execute("DROP TABLE label_lists")
        store.connection.execute("PRAGMA user_version = 2")
    store.close()

    migrated = MatchStore(path)
    try:
        assert migrated.connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert migrated.summary("player").wins == 1
        assert migrated.evaluation("game") == Evaluation.NOT_EVALUATED
        assert len(migrated.sessions("player")) == 1
    finally:
        migrated.close()


def test_evaluation_should_enforce_valid_states_in_database() -> None:
    store = MatchStore(":memory:")
    try:
        store.set_evaluation("game", Evaluation.POSSIBLE, TIMESTAMP)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            store.connection.execute("UPDATE match_labels SET label_id = 'certain'")
        store.connection.rollback()
        assert store.evaluation("game") == Evaluation.POSSIBLE
    finally:
        store.close()
