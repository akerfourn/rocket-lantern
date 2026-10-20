# RocketLantern 1.6.0

Customize match labels and choose exactly what appears in your overlay.

## Categories and match labels

- Create independent annotation categories with custom labels. Each match
  can have one label per category, editable during play or in history.
- Manage categories and labels in a dedicated window. Rename, reorder or
  disable them without erasing historical annotations.
- Choose a Tag, Flag or Shield icon family for each category, then set
  each label's name, color, inner symbol and optional keyboard shortcut.
- Existing smurf assessments become the default category and keep their
  saved choices and shortcuts.
- Global shortcuts are enabled by default on new installations. Existing
  explicit preferences are preserved. Apply label edits to update bindings
  automatically; leave a shortcut empty to use mouse editing only.

## Overlay customization

- Independently show or hide wins, losses and the signed delta.
- Add selected annotation categories to the W/L overlay. Their icons follow
  the current or last match's labels, including changes made by shortcuts.
- Adjust each overlay's opacity from 10 to 100%, including its background,
  text and icons. Settings are remembered and reflected in the preview.
- Anchor custom positions to the left edge, center or right edge, so that
  point stays fixed when the overlay content gets wider.
- Find the placement preview with a brief animated marker. The controls
  become semi-transparent when the preview passes behind them.
- Open W/L overlay settings directly from the summary banner's detach
  button, without enabling the overlay.

## Fixes

- Determine match results from the player's latest playing team in that
  match, including private matches and subsequent spectator transitions.
  Do not reuse the previous match's team. Previously saved results are not
  recalculated.
- Preserve Unicode account names when reading Rocket League logs and
  refresh displayed and saved names from Stats API updates.

## Updating and Windows packages

Close RocketLantern and back up its local data before updating. On first
launch, the database migrates automatically from schema 3 to schema 5,
preserving history, assessments and preferences. Older releases cannot
open the migrated database; keep the backup if you may need to downgrade.

- `RocketLantern-1.6.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.6.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Use Rocket League's
**Borderless** or **Windowed** display mode for overlays. Executables
remain unsigned; Windows may display a SmartScreen warning.
