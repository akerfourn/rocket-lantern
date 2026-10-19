# RocketLantern 1.5.0

RocketLantern now detects the running game and your connected account,
and lets you restrict the teammate boost overlay to private play.

## Automatic game and account detection

- Connect to the Stats API when Rocket League starts and stop connection
  attempts when it closes.
- Show overlays only while Rocket League is visible in the foreground.
  Alt+Tab and minimizing the game hide overlays without interrupting
  match tracking or the API connection.
- Detect the primary Steam or Epic account from Rocket League's local
  startup log and follow account changes automatically.
- Keep manual player selection available when account detection fails.
- When an account is detected, use the Player selector to browse history
  without changing the tracked account or the team shown by boost gauges.
- Clear stale boost data when the detected account changes.

## Teammate boost overlay

- Replace the on/off setting with **Never** (the default), **Private
  matches only**, and **All matches**.
- Include private matches, local/LAN play, online free play and recognized
  offline or training modes in the private-only option.
- Exclude public matchmaking, including casual playlists, and tournaments
  from private-only mode. Unknown game modes keep the overlay hidden.
- Apply the selection immediately and remember it between launches.
  Previously enabled boost overlays retain **All matches**; the existing
  risk acknowledgment remains required.
- Recognize online free play in game-mode labels.

French and English setup instructions and user documentation have been
updated for these changes.

## Updating and Windows packages

Close RocketLantern before installing. Existing history, statistics,
match assessments and preferences are preserved. The database remains at
schema version 3; these settings do not require a database migration.

- `RocketLantern-1.5.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.5.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Use Rocket League's
**Borderless** or **Windowed** display mode for overlays. Executables
remain unsigned; Windows may display a SmartScreen warning.
