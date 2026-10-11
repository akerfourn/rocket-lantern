"""Pure release selection and download validation for the official repository."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

REPOSITORY = "akerfourn/rocket-lantern"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases"
RELEASE_URL = f"https://github.com/{REPOSITORY}/releases/"
MAX_DOWNLOAD_SIZE = 250 * 1024 * 1024
CHANNELS = ("disabled", "stable", "all")


def version_key(version: str) -> tuple[int, int, int, int, int] | None:
    """Compare supported stable and Python/SemVer alpha, beta and rc versions."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(alpha|beta|a|b|rc)[-.]?(\d+))?", version)
    if match is None:
        return None
    stage = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, None: 3}[match[4]]
    sequence = 0
    if match[5] is not None:
        sequence = int(match[5])
    return (int(match[1]), int(match[2]), int(match[3]), stage, sequence)


@dataclass(frozen=True)
class UpdateRelease:
    """Validated release metadata; executable downloads require a SHA-256 digest."""

    version: str
    page_url: str
    unstable: bool
    download_url: str = ""
    digest: str = ""
    size: int = 0


def installer_asset(value: object) -> tuple[str, str, int]:
    """Reject untrusted URLs, oversized packages and missing integrity metadata."""
    if not isinstance(value, list):
        return ("", "", 0)
    for asset in value:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        digest = asset.get("digest", "")
        size = asset.get("size")
        if not isinstance(name, str) or not re.fullmatch(
            r"RocketLantern-[\w.-]+-windows-x64-setup\.exe", name
        ):
            continue
        if not isinstance(url, str) or not url.startswith(RELEASE_URL + "download/"):
            continue
        parsed = urlsplit(url)
        if parsed.query or parsed.fragment or parsed.username is not None:
            continue
        if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            continue
        if type(size) is not int or not 0 < size <= MAX_DOWNLOAD_SIZE:
            continue
        return (url, digest.removeprefix("sha256:"), size)
    return ("", "", 0)


def select_update(value: object, current: str, channel: str) -> UpdateRelease | None:
    """Choose the highest newer version, never dates or a downgrade."""
    current_key = version_key(current)
    if channel not in ("stable", "all") or current_key is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Expected a GitHub release list")
    best_key = current_key
    best = None
    for release in value:
        if not isinstance(release, dict) or release.get("draft") is not False:
            continue
        tag = release.get("tag_name")
        page = release.get("html_url")
        if not isinstance(tag, str) or not isinstance(page, str):
            continue
        key = version_key(tag)
        if key is None or key <= best_key or page != RELEASE_URL + "tag/" + tag:
            continue
        unstable = release.get("prerelease") is True or key[3] != 3
        if channel == "stable" and unstable:
            continue
        url, digest, size = installer_asset(release.get("assets"))
        best = UpdateRelease(tag.removeprefix("v"), page, unstable, url, digest, size)
        best_key = key
    return best
