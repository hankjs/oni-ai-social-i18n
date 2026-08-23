# Contributing to oni-ai-social-i18n

This repository is the **only edit source** for player-visible UI strings and
storylet/fallback dialogue for ONI Social Life. Git is the only persistence.

## Locales

- Source locale is `zh`. Do not rename or delete keys.
- Published locales (`manifest.json` `publishedLocales`) must be complete:
  no missing, draft, or stale entries.
- Translation token sets (`{0}`, `{actor}`, …) must match the source.
- Dialogue translations align by `candidateId` + `turnId`, never by array index.
  Candidate / turn / speaker-slot structure must match source.

## Workflow

1. Branch from `main` as `i18n/<locale>/<yyyyMMdd>-<slug>` or `source/<yyyyMMdd>-<slug>`.
2. Edit `catalog/` (Chinese source) or `locales/<locale>/` (translations).
   Do not hand-edit `dist/`.
3. Run `python3 tools/export.py` and `python3 tools/validate.py`.
4. Commit source JSON **and** regenerated `dist/` together.
5. Open a pull request. `main` only accepts PRs.
6. Normal development leaves `manifest.json` `contentVersion` at the currently published Mod
   version; repeated content commits do not consume release numbers.
7. Only when the maintainer explicitly starts a release do they update `contentVersion` and tag
   the reviewed `main` commit as `i18n-vX.Y.Z`. The suffix must equal the manifest and tags are
   immutable.

Fork/PR from GitHub remains a valid contribution path. The web editor (Phase 2)
does not replace this workflow.

## What not to change here

Gameplay rules, probabilities, speaker selection, trait-tag matching, and LLM
output protocols stay in the private Mod repository. Prompt locked-token
migration is Phase 4 and is not open as a pure translation change.
