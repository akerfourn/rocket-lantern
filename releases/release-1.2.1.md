# RocketLantern 1.2.1

This patch corrects misleading startup error messages and makes failures
easier to diagnose, including with portable installations.

## Fixes

- Distinguish missing application files, data access, migration, SQLite,
  translation and launch errors instead of reporting every failure as a
  local database problem.
- Show the failing step, application version, relevant paths, exact
  exception and traceback. **Copy diagnostic** copies the full details
  without closing the error window. Nothing is uploaded automatically.
- Keep the error window usable even when packaged icons or translation
  files are missing, with French and English messages when available.
- Give appropriate guidance for complete portable extraction, denied
  permissions and locked databases, without suggesting data deletion or
  disabling antivirus protection.
- Close SQLite connections when schema initialization fails, avoiding
  leaked connections after an unsuccessful startup.

The absence of a database is normal on first launch: RocketLantern creates
it automatically. A startup failure still needs its diagnostic to identify
the actual cause; this release does not assume an antivirus is responsible.

## Updating

Close RocketLantern before installing this release. Existing history,
statistics, assessments and preferences are preserved. The database schema
is unchanged from version 1.2.0.

Diagnostics can include your Windows account name in file paths. Review
them before posting publicly.

## Windows packages

- `RocketLantern-1.2.1-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.2.1-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning. Updates and uninstallation
preserve local data.
