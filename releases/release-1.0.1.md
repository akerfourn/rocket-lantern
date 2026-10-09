# RocketLantern 1.0.1

RocketLantern now stores its data under its own name and automatically
migrates existing installations when the application starts.

## Changes

- Use `%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3` for local
  history, match statistics and preferences on Windows.
- Detect the previous data directory automatically at startup, before
  opening the database. No manual migration or separate script is required.
- Copy existing files and validate their contents and SQLite integrity
  before removing originals. Committed SQLite WAL data is preserved.
- Resume interrupted cleanup on the next launch. Changed files stop cleanup
  rather than risking data loss.
- Preserve both databases if data already exists at the new location;
  existing data is never automatically overwritten or merged.
- Recommend `PacketSendRate=10` for smoother live updates, and show the
  current data path in user documentation.

## Updating

Close all running RocketLantern instances, then install or extract the new
version. Launch it normally: history, statistics and preferences are
migrated automatically. Original files are deleted only after the copied
data is verified.

If migration cannot finish because of locked files or missing permissions,
the application stops with an error. Close other instances and retry.
Copied data remains available, and unfinished cleanup is retried at startup.

## Windows packages

- `RocketLantern-1.0.1-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.0.1-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning. Updates and uninstallation
preserve local data.
