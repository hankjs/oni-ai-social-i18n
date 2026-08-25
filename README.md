# oni-ai-social-i18n

Public schema-v2 content for ONI Social Life. There is no source language: `zh`, `en`, and
future locales use the same authoring model.

- `contracts/` owns language-neutral UI keys, prompt IDs, storylets, Chronicle pools and slots.
- `locales/<locale>/` owns that locale's complete text, Dialogue candidates and Chronicle
  templates. Candidate/template IDs are stable only within their locale.
- `links/` records optional translation/adaptation provenance and never enters runtime identity.
- `dist/` is deterministic generated runtime input. Never edit it by hand.
- `manifest.json` alone controls locale lifecycle and shipping. `stable` and `preview` may ship;
  `draft` never does.

Run `python3 tools/validate.py` for authoring plus release-quality validation,
`python3 tools/export.py` to regenerate the frozen files, and `make check` before review.

## Fallback boundaries

UI and Prompt resolve one key at a time. Dialogue resolves one complete `storyletId` pool;
Chronicle resolves one complete `poolId`. Resolved exports always record `resolvedLocale`, so a
fallback pool cannot masquerade as requested-locale content or mix languages inside one unit.

Stable locales require 100% native critical UI/Prompt content, at least 95% native standard
content, and native minimums for every required Dialogue/Chronicle pool. Preview locales may
fallback by unit. Draft and stale entries are structurally validated but excluded from dist.

## Chronicle stability and compatibility

Each locale has `stability/chronicle.json`. Published `(locale, templateId)` identities are never
reused; retired templates stay present with `deprecated: true`. Old-save mappings live under
`contracts/compatibility/` and the frozen compatibility dist. Compatibility does not require a
new locale to copy historical zh/en IDs.

During development, `contentVersion` follows the tracked Mod/i18n pairing. Only the maintainer's
explicit release operation creates immutable `i18n-vX.Y.Z` tags; Mod and i18n must be released as
one reviewed pairing.
