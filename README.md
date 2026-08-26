# oni-ai-social-i18n

Public schema-v2 content for ONI Social Life. Runtime contracts are language-neutral, while
reviewed Simplified Chinese (`zh`) is the sole editorial and translation source. The complete
stable release set is `zh`, `en`, `ko`, `ru`, `ja`, and `vi`.

- `contracts/` owns language-neutral UI keys, prompt IDs, storylets, Chronicle pools and slots.
- `locales/<locale>/` owns that locale's complete text, Dialogue candidates and Chronicle
  templates. Candidate/template IDs are stable only within their locale.
- `links/` records optional translation/adaptation provenance and never enters runtime identity.
- `provenance/` binds every non-Chinese content file to the exact reviewed Chinese source hash;
  stale source or target hashes block stable/shipped locales.
- `glossary.json` owns terminology across all six planned release languages. A `null` target
  term means that language has not yet received an approved translation.
- `dist/` is deterministic generated runtime input. Never edit it by hand.
- `manifest.json` alone controls locale lifecycle and shipping. Only complete `stable` locales
  ship; machine-generated `draft` content never does.

Run `python3 tools/validate.py` for authoring plus release-quality validation,
`python3 tools/export.py` to regenerate the frozen files, and `make check` before review.

Translate and review the target locale directly in the same JSON structure as the Chinese source.
Keeping IDs, turns, slots, variables and scene context in place avoids a lossy export/re-import step.
Review evidence is recorded separately; only approved JSON changes may advance authoring status.

## Fallback boundaries

UI and Prompt resolve one key at a time. Dialogue resolves one complete `storyletId` pool;
Chronicle resolves one complete `poolId`. Resolved exports always record `resolvedLocale`, so a
fallback pool cannot masquerade as requested-locale content or mix languages inside one unit.

Stable locales require 100% exact native UI and Prompt content plus an exact native pool for
every Dialogue storylet and Chronicle pool. Any normal fallback is a release error. Draft and
stale entries remain structurally validated but are excluded from dist.

## Chronicle stability and compatibility

Every locale has `stability/chronicle.json`. Published `(locale, templateId)` identities are never
reused; retired templates stay present with `deprecated: true`. Old-save mappings live under
`contracts/compatibility/` and the frozen compatibility dist. Compatibility does not require a
new locale to copy historical zh/en IDs.

During development, `contentVersion` follows the tracked Mod/i18n pairing. Only the maintainer's
explicit release operation creates immutable `i18n-vX.Y.Z` tags; Mod and i18n must be released as
one reviewed pairing.
