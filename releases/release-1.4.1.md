# RocketLantern 1.4.1

This patch remembers your overlay choices between launches and simplifies
their settings.

## Fixes and improvements

- Restore the enabled or disabled state of each overlay independently
  when RocketLantern starts.
- Remember acceptance of the teammate boost warning, so it does not need
  to be confirmed again at every launch. Automatic activation still
  requires a previously saved acceptance.
- Keep overlay preferences when live data stops or a screen becomes
  temporarily unavailable.
- Remove development diagnostic controls and per-overlay explanations.
  A shared note recommends **Borderless** or **Windowed** mode if an
  overlay does not appear in fullscreen.
- Update French and English labels and user guides.

## Updating and Windows packages

Close RocketLantern before installing. Existing history, statistics,
assessments and preferences are preserved; the database schema is unchanged.

- `RocketLantern-1.4.1-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.4.1-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning.
