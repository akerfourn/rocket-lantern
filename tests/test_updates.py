"""Release selection is deterministic and never contacts GitHub."""

import hashlib

import pytest

from rocket_lantern.updates import RELEASE_URL, installer_asset, select_update, version_key


def release(tag: str, *, preview: bool = False, draft: bool = False) -> dict[str, object]:
    return {
        "tag_name": tag,
        "prerelease": preview,
        "draft": draft,
        "html_url": RELEASE_URL + "tag/" + tag,
        "assets": [],
    }


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("1.0.9", "1.0.10"),
        ("1.1.0-alpha.9", "1.1.0-beta.1"),
        ("1.1.0b2", "1.1.0-rc.1"),
        ("1.1.0rc9", "1.1.0"),
        ("1.1.0", "1.2.0-alpha.1"),
    ],
)
def test_version_should_compare_semantically(older: str, newer: str) -> None:
    assert version_key(older) < version_key(newer)


def test_version_should_treat_python_and_tag_spellings_as_equal() -> None:
    assert version_key("v1.1.0-beta.1") == version_key("1.1.0b1")


@pytest.mark.parametrize("channel", ["disabled", "invalid"])
def test_selection_should_not_offer_update_when_channel_is_disabled(channel: str) -> None:
    assert select_update([release("v2.0.0")], "1.0.0", channel) is None


def test_selection_should_ignore_previews_drafts_and_release_order_for_stable() -> None:
    values = [
        release("v9.0.0", draft=True),
        release("v3.0.0", preview=True),
        release("v4.0.0-alpha.1"),
        release("v2.0.0"),
        release("v1.5.0"),
    ]
    update = select_update(values, "1.0.0", "stable")
    assert update is not None
    assert update.version == "2.0.0"
    assert not update.unstable


def test_selection_should_include_stable_and_preview_in_all_channel() -> None:
    values = [release("v1.1.0"), release("v1.2.0-rc.1", preview=True)]
    update = select_update(values, "1.0.0", "all")
    assert update is not None
    assert update.version == "1.2.0-rc.1"
    assert update.unstable


@pytest.mark.parametrize("current", ["1.2.0", "1.2.0b1", "2.0.0", "invalid"])
def test_selection_should_never_offer_equal_versions_or_downgrades(current: str) -> None:
    assert select_update([release("v1.2.0-beta.1", preview=True)], current, "all") is None


def test_selection_should_reject_untrusted_release_page() -> None:
    value = release("v2.0.0")
    value["html_url"] = "https://evil.example/download"
    assert select_update([value], "1.0.0", "stable") is None


def valid_asset() -> dict[str, object]:
    return {
        "name": "RocketLantern-2.0.0-windows-x64-setup.exe",
        "browser_download_url": RELEASE_URL + "download/v2.0.0/setup.exe",
        "digest": "sha256:" + hashlib.sha256(b"test").hexdigest(),
        "size": 4,
    }


def test_asset_should_require_official_url_and_integrity_metadata() -> None:
    value = valid_asset()
    assert installer_asset([value]) == (
        value["browser_download_url"],
        hashlib.sha256(b"test").hexdigest(),
        4,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("digest", None),
        ("digest", "sha256:bad"),
        ("size", 0),
        ("size", 1000000000),
        ("size", True),
        ("browser_download_url", "https://evil.example/setup.exe"),
        ("browser_download_url", "http://github.com/akerfourn/rocket-lantern/setup.exe"),
        ("name", "malware.exe"),
    ],
)
def test_asset_should_reject_unsafe_download(field: str, value: object) -> None:
    asset = valid_asset()
    asset[field] = value
    assert installer_asset([asset]) == ("", "", 0)


def test_selection_should_report_missing_installer_for_manual_download() -> None:
    update = select_update([release("v2.0.0")], "1.0.0", "stable")
    assert update is not None
    assert update.download_url == ""


def test_selection_should_reject_invalid_metadata_response() -> None:
    with pytest.raises(ValueError, match="GitHub release list"):
        select_update({"message": "rate limited"}, "1.0.0", "stable")
