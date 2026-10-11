# RocketLantern 1.1.0

This release adds built-in update detection, a dedicated settings window,
and tools to check and configure Rocket League's Stats API across multiple
Steam and Epic Games installations.

## New features

### Settings

- Open a dedicated settings window from the main toolbar, with an icon
  button and an explicit **Close** button.
- Configure the local connection port and reconnect from the same window.
- Switch between French and English instantly.
- Choose **Matches** or **Live match** as the startup tab.
- View the installed version and open the GitHub releases page.
- Keep the window compact until configuration results appear; its height
  adapts to the results and available screen space.

### Update detection

- Choose **Disabled**, **Stable updates** (default), or
  **All updates (unstable)**, with a warning for development versions.
- Check GitHub releases at startup, every ten minutes, or manually using
  **Check now**. Disabled update detection makes no update requests.
- Show a download button beside the application name when a newer version
  is available: green for stable releases, orange for previews.
- Ask for confirmation before downloading or opening a release page.
- For installed Windows versions, verify the downloaded installer's size
  and SHA-256 digest before opening the installation wizard. Portable and
  source versions use the release page for manual updates.

### Rocket League configuration

- Detect Steam installations across multiple library folders and Epic
  Games installations using local launcher metadata and known locations.
  Searches run only when requested, without scanning entire drives.
- Open each installation's `TAGame\Config` folder directly.
- Save a desired `PacketSendRate`, defaulting to **10 packets per second**.
- Check each installation separately: a lower rate warns of potentially
  delayed live updates; an equal rate is conforming; a higher rate is
  informational and already provides sufficient periodic updates.
- Apply the desired rate individually to differing installations.
  Preserve other settings, comments, file encoding and line endings, and
  save a backup beside the INI file.
- Refuse unsafe changes to unreadable or ambiguous configurations, or to
  files changed since the last check.

## Improvements and fixes

- Separate teams in the live player table, place the selected player's
  team first, and sort each team by descending score.
- Always show a sign for the W/L difference, including **+0**.
- Fix upgrades reporting an older version because stale package metadata
  remained in the installation directory.
- Strengthen Windows package and release publication checks, including
  isolated installation, upgrade, uninstallation and portable launch tests.

## Updating and configuration notes

Close RocketLantern before installing this release. Existing match history,
statistics and preferences are preserved.

Close Rocket League before applying configuration changes, then restart
it. Changing the desired rate alone never edits game files. Checks report
installation-file values, not a measurement of the running game's rate;
an existing user configuration can override them. Only `PacketSendRate`
is changed automatically: configure `WebPort` separately if needed.

## Windows packages

- `RocketLantern-1.1.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.1.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning. Updates and uninstallation
preserve local data.
