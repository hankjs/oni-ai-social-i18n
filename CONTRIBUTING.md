# Contributing to oni-ai-social-i18n

Git is the only persistence for player-visible content. Schema v2 separates language-neutral
contracts from locale-owned writing.

## What to edit

- Change `contracts/` only when gameplay meaning, slots, arguments, quality thresholds or a
  contract revision changes.
- Add visible copy under `locales/<locale>/`. A locale may have candidates/templates that no
  other locale has, with different IDs, counts, turns, weights and slot choices.
- Add optional provenance in `links/` with `translationOf`, `adaptationOf` or `inspiredBy`.
- Never add placeholders for missing translations and never hand-edit `dist/`.

UI/Prompt entries use their global key/ID and current `contractRevision`. Dialogue candidate
identity is `(locale,candidateId)`; Chronicle identity is `(locale,templateId)`. Within a locale,
IDs and ordinals are permanent. Retire a published Chronicle template with `deprecated: true`
and preserve the locale stability high-water mark.

## Workflow

1. Branch from `main` as `i18n/<locale>/<yyyyMMdd>-<slug>` or
   `contract/<yyyyMMdd>-<slug>`.
2. Edit contracts or locale files.
3. Run `python3 tools/validate.py` and `python3 tools/export.py`.
4. Run `make check`; commit authoring and regenerated `dist/` together.
5. Open a pull request. Missing cross-language counterparts are valid; structural, placeholder,
   stability and locale quality failures are not.
6. Only an explicit coordinated release creates the immutable `i18n-vX.Y.Z` tag.

Gameplay rules and numeric effects remain in the private Mod repository. Locale selection
criteria choose writing only and never modify SocialCore state or consume its RNG.
