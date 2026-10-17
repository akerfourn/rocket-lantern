# RocketLantern 1.3.0

This release adds a first-run setup guide and quieter, lighter diagnostic
logs.

## First-run setup

- Open the setup guide automatically for new users. Existing users with
  a selected player or saved matches are not prompted.
- Choose the language and local port, find Steam and Epic Games
  installations, and configure `PacketSendRate` from one window.
- Keep searches and INI changes explicit. Applying a setting creates a
  backup; the game's `WebPort` still needs to be checked manually.
- Remember whether the guide was finished or skipped, and reopen it at
  any time from **Settings → Setup guide**.
- Save discovered installation paths locally. Restored paths are marked
  as requiring a fresh check before applying changes; no installation
  scan runs automatically at startup or on a timer.
- Update French and English labels immediately, and keep navigation
  buttons accessible on smaller screens.

## Diagnostic logs

- Keep connection messages, errors, saved results and major match events
  without dumping every live state update.
- Add an **API details** checkbox for troubleshooting. It includes all
  events and their redacted JSON contents, and is off at each launch.
- Limit the journal to 300 entries and truncate message details after
  2,000 characters, reducing the amount of text retained in memory.
- Continue processing every API message for tracking and live views,
  regardless of logging verbosity. Logs are not saved automatically.

## Updating

Close RocketLantern before installing this release. Existing history,
statistics, assessments and preferences are preserved. The database
schema remains at version 3; the new setup preferences use the existing
settings table.

## Windows packages

- `RocketLantern-1.3.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.3.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning. Updates and uninstallation
preserve local data.
