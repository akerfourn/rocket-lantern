"""Synthetic startup logs: no credentials or files from the real game are used."""

from pathlib import Path

import pytest

from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog, parse_login


def login(
    primary_id: str = "Steam|123|0", name: str = "Player", status: str = "LS_LoggedIn"
) -> str:
    return (
        "[0006.53] Party: HandleLocalPlayerLoginStatusChanged "
        f"PlayerName={name} PlayerID={primary_id} LoginStatus={status} "
        "IsPrimary=True IsInParty=False\n"
    )


@pytest.mark.parametrize("primary_id", ["Steam|123|0", "Epic|abcdef123|0"])
def test_login_should_identify_the_primary_account_by_id_not_display_name(primary_id: str) -> None:
    assert parse_login(login(primary_id, "Name with spaces · É")) == (
        True,
        LocalPlayer(primary_id, "Name with spaces · É"),
    )


@pytest.mark.parametrize(
    "line",
    [
        "Log: Command line: -epicusername=NotTheAccount\n",
        login().replace("IsPrimary=True", "IsPrimary=False"),
        login("Steam|123|1"),
        "An unrelated line containing " + login(),
        login().replace("Party:", "Auth:"),
    ],
)
def test_login_should_ignore_other_players_and_unrelated_lines(line: str) -> None:
    assert parse_login(line) == (False, None)


@pytest.mark.parametrize("primary_id", ["Steam|123|0", "Unknown|0|0"])
def test_login_should_revoke_identity_on_primary_logout(primary_id: str) -> None:
    assert parse_login(login(primary_id, status="LS_NotLoggedIn")) == (True, None)


def test_log_should_wait_for_a_complete_line_and_follow_account_switches(tmp_path: Path) -> None:
    path = tmp_path / "Launch.log"
    line = login()
    path.write_text(line[:-5], encoding="utf-8")
    source = LocalPlayerLog(path)
    assert source.read() is None
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line[-5:])
    assert source.read() == LocalPlayer("Steam|123|0", "Player")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(login("Epic|abcdef|0", "Other"))
    assert source.read() == LocalPlayer("Epic|abcdef|0", "Other")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(login("Unknown|0|0", status="LS_NotLoggedIn"))
    assert source.read() is None


def test_log_should_reset_after_truncation_and_replacement(tmp_path: Path) -> None:
    path = tmp_path / "Launch.log"
    path.write_text(login() * 3, encoding="utf-8")
    source = LocalPlayerLog(path)
    assert source.read() == LocalPlayer("Steam|123|0", "Player")
    path.write_text(login("Epic|abc|0", "Other"), encoding="utf-8")
    assert source.read() == LocalPlayer("Epic|abc|0", "Other")
    replacement = tmp_path / "replacement.log"
    replacement.write_text("Log: Starting a new session\n", encoding="utf-8")
    replacement.replace(path)
    assert source.read() is None


def test_log_should_not_hold_a_handle_or_keep_identity_when_removed(tmp_path: Path) -> None:
    path = tmp_path / "Launch.log"
    path.write_text(login(), encoding="utf-8")
    source = LocalPlayerLog(path)
    source.read()
    path.unlink()
    assert source.read() is None
    assert source.ready


def test_log_should_bound_reads_and_skip_overlong_lines_without_retaining_their_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rocket_lantern.local_player.MAX_READ_BYTES", 1024)
    path = tmp_path / "Launch.log"
    path.write_text("x" * 10000 + "\n" + login(), encoding="utf-8")
    source = LocalPlayerLog(path)
    assert source.read() is None
    assert not source.ready
    assert source._offset == 1024
    for _ in range(12):
        source.read()
        assert len(source._pending) <= 4096
    assert source.ready
    assert source.player == LocalPlayer("Steam|123|0", "Player")


def test_log_should_reject_a_file_older_than_the_current_game_session(tmp_path: Path) -> None:
    path = tmp_path / "Launch.log"
    path.write_text(login(), encoding="utf-8")
    source = LocalPlayerLog(path)
    assert source.read(path.stat().st_mtime + 1) is None
    assert source.player is None
