# Contributing to oni-ai-social-i18n

This repository is the **only edit source** for player-visible UI strings and
Storylet dialogue for ONI Social Life. Git is the only persistence. Dialogue source
candidates carry explicit actor affect/voice/scene selection and a same-tier weight.

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
6. During development, `manifest.json` `contentVersion` follows the Mod's tracked development
   version. Repeated commits may reuse that version and do not create tags or claim it is online.
7. Only when the maintainer explicitly starts a release do they tag the reviewed `main` commit as
   `i18n-vX.Y.Z`. The suffix must equal the manifest and tags are immutable.

Fork/PR from GitHub remains a valid contribution path. The web editor uses the same files and
validator; it does not replace review through Git.

## What not to change here

Gameplay rules, event-to-affect classification, numeric relationship effects, and LLM output
protocols stay in the private Mod repository. Content authors may declare which classified
emotion, intensity, stance, voice, relationship, cause, or actor slot a candidate is written for;
those declarations only select copy and never change gameplay state.
