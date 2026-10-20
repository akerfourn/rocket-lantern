# RocketLantern 1.6.1

Keep player history accessible after closing Rocket League.

## Offline browsing and player favorites

- Preserve the history selection when the game closes. Browsing another
  player offline no longer replaces the tracked account or live player.
- Use the star next to the Player selector to add or remove a favorite.
  Favorites appear first and remain available between launches.
- Open **Settings → General → Manage favorite players** to search saved
  match participants by name or identifier and bookmark earlier teammates,
  opponents or accounts.
- Keep non-favorite players from older matches out of the main selector.
  The search window provides access to them without cluttering the list.
- Remember the last history selection independently of account detection.
  Choosing a favorite does not change the detected account or boost team.

Favorites use existing local data; no online player lookup or statistics
download is performed.

## Updating and Windows packages

Close RocketLantern before updating. Existing history, assessments and
preferences are preserved. Updating from 1.6.0 does not change the database
schema; favorites are stored as local preferences.

- `RocketLantern-1.6.1-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.6.1-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning.
