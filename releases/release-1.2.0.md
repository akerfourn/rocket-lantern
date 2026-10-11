# RocketLantern 1.2.0

This release adds manual match assessments and optional Windows global
shortcuts to record your impressions without leaving Rocket League.

## New features

### Manual match assessments

- Assess a match as **Not evaluated** (default), **No suspicion**,
  **Possible smurf**, or **Strong suspicion**.
- Click the icon-only tag immediately after the W/L delta to open the
  selector. Change your choice at any time during the match.
- Keep the last observed match editable after it ends, until a new
  identified match arrives. Each new match starts unreviewed.
- Edit previous matches using the compact tags in match history.
- Distinguish choices with both colors and interior symbols: dash, check,
  question mark and exclamation mark. Hover for the textual label.
- Translate tooltips and menus instantly between French and English.
- Save choices locally in SQLite, linked to the match's internal ID.
  Assessments are independent of player selection, sessions and filters;
  they do not change W/L results or send reports to Epic.

These are personal observations, not automatic detections or proof of
smurfing. Mouse editing works without configuring any shortcuts.

### Optional global shortcuts on Windows

- Enable and configure shortcuts in **Settings**, then click
  **Apply shortcuts**. They are disabled by default.
- Use **Ctrl+Shift+F1** for **Not evaluated**, **F2** for **No suspicion**,
  **F3** for **Possible smurf**, and **F4** for **Strong suspicion**, always
  with **Ctrl+Shift** held down.
- Target the current or last observed match, never a selected history row.
- Pause shortcuts while the settings window is open; resume the saved
  configuration when it closes.
- Reject duplicate or unsupported combinations and report registration
  conflicts. If any shortcut cannot be registered, none remains active.

Shortcuts use Windows' `RegisterHotKey` API and Qt's native event handling,
without keyboard hooks, continuous keystroke recording or game injection.

## Interface improvements

- Keep assessment tags icon-only, without permanent labels or dropdown
  arrows, in both the W/L banner and match history.
- Let settings expand for shortcut controls and scroll on smaller screens,
  keeping the **Close** button visible.

## Updating and data compatibility

Close RocketLantern before installing this release. Existing history,
statistics and preferences are preserved. The first launch automatically
upgrades the local database to schema 3 to store match assessments.

Older releases supporting only schema 2 cannot open the upgraded database.
Back up your local data before the first launch if you may need to roll
back to an older version.

## Windows packages

- `RocketLantern-1.2.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.2.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning. Updates and uninstallation
preserve local data.
