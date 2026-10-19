# RocketLantern contributor instructions

## Scope and working tree

- Follow the user's global instructions as well as this file.
- Answer the user in their language. Write release notes in English.
- Preserve unrelated work, including uncommitted features. Do not stage
  everything when preparing a release fix.
- Never commit, move tags, push or publish without explicit authorization.

## Version changes are release preparation

Do not treat a version bump as a change to `pyproject.toml` alone.

For every requested version change:

1. Read the current version, Git status and relevant commits.
2. Update `pyproject.toml` and the application's version in `uv.lock`.
   The lockfile may normalize `1.5.0-alpha.2` to `1.5.0a2`; these represent
   the same version. Do not update unrelated dependencies.
3. For a **stable** version, create or update
   `releases/release-<version>.md` in the same change. For example,
   `1.5.0` requires `releases/release-1.5.0.md`, without a `v` prefix.
   A stable version bump is incomplete without its release notes, even
   when the user did not explicitly ask for them.
4. For an **alpha, beta or release candidate**, check that
   `releases/prerelease.md` remains appropriate. The workflow uses that
   standard message; do not create individual preview notes unless asked.
5. Synchronize the local editable package metadata before testing its
   reported version. Use the declared version, not the normalized lockfile
   spelling, for `--expected-version`.
6. Run the relevant checks below and report their actual results.

## Release note content

- Summarize observable changes since the previous stable release.
- Inspect the commits being released; do not copy the conversation or
  include unrelated/uncommitted features.
- When repairing an existing tag, describe that tag's contents, not the
  entire current working tree.
- Cover migration, compatibility and upgrade precautions when applicable.
- List the exact Windows installer and portable archive filenames.
- Keep wording factual and concise. Use Markdown with UTF-8, LF endings
  and lines of at most 80 characters, except long reference URLs.
- The file is the GitHub release body; do not replace it with the commit
  message, a placeholder or an empty heading.

## Build and publication rules

- Stable publication is triggered by `vMAJOR.MINOR.PATCH` tags, regardless
  of branch. The tag must match `pyproject.toml` exactly and contain its
  nonempty release note in the tagged commit.
- Preview publication is triggered by a branch push that changes the
  version to an alpha, beta or release candidate. An unchanged preview
  version must not create another publication.
- Manual recovery uses **Actions → Windows build → Run workflow**, with
  the existing stable tag in `release_tag`.
- All stable jobs check out the requested tag, including the release-note
  check. Adding notes only to `main` cannot repair a tag without them.
- Rerunning an old execution is not a way to include a new fix commit.
  Explain this before recommending a rerun.
- Never silently move a published tag. Prefer a new patch release when
  the original version was already published. If an unpublished tag needs
  repair, explain the options and obtain authorization before changing it.
- Never publish packages built from unrelated local changes under an
  existing stable version.

## Validation

Run local tests without asking for unnecessary manual confirmation. Use
the configured permission mechanism if sandbox access is required.

For version changes and release-note fixes:

```powershell
uv sync --locked --group build
uv run --locked pytest -q tests/test_release_workflow.py
uv run --locked ruff check .
uv run --locked ruff format --check .
git diff --check
```

For application changes, also compile changed translations and run the
full test suite:

```powershell
uv run --locked python scripts/compile-translations.py
uv run --locked pytest -q
```

For Windows packaging or publication changes, use the existing scripts:

```powershell
./scripts/build-windows.ps1
./scripts/test-windows-packages.ps1 -PackageVersion '<declared-version>'
```

Supply the installed `uv` or Inno Setup path if they are not on `PATH`.
Package tests use an isolated installation. Publication tests intercept
GitHub CLI calls: a successful dry run does not mean a release was uploaded.
Do not claim a complete pipeline success if any step failed or was skipped.
