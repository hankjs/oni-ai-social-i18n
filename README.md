# oni-ai-social-i18n

Public catalog for ONI Social Life player-visible strings.

- Source locale: `zh`
- Published locales: `zh`, `en`
- Edit `catalog/` and `locales/`; never hand-edit `dist/`
- `python3 tools/export.py` regenerates `dist/`
- `python3 tools/validate.py` checks uniqueness, tokens, dialogue structure, and chronicle pools

## Structured dialogue copy

Dialogue source lives in `catalog/dialogue/` and translations in
`locales/<locale>/dialogue/`. Every candidate belongs to a real `storyletId`, contains its full
ordered turn plan, and declares a `selection` over actor slot (`-1` means any actor), primary or
secondary emotion, intensity, social stance, personality voice, relationship state, and cause.
The shared runtime always chooses the highest-specificity matching tier, then applies candidate
weight and its recent-use window. Empty selection is the storylet's base candidate, not a second
fallback pipeline. All dimension values are schema-enumerated so authoring typos fail validation.

## Structured chronicle copy

Detailed chronicle sentences are not UI `LocString` keys. Their Chinese source lives in
`catalog/chronicle/`, translations in `locales/<locale>/chronicle/`, and deterministic runtime
catalogs in `dist/chronicle/`.

Each pool declares a stable `poolId`, a release-blocking `minimumPublished`, and its allowed slot
contract. Each complete sentence has a permanent `templateId`; published ids may be deprecated
but are never reused, so old saves remain readable. `contracts/chronicle-stability.json` records
the allocated id high-water mark for every persisted pool; removing an id or adding one without
registering it fails validation. Locale entries must preserve placeholders, carry a current
`sourceHash`, and be reviewed.

The canonical Chronicle authoring layout contains six active family files (`routine`, `support`,
`relationship`, `colony`, `dark`, `connective`) plus
`compatibility/legacy-pair.json`. The current complete snapshot has 137 pools, 976 reviewed active
templates and 120 deprecated `{pair}` templates retained only for persisted IDs. Parallel `v2-*`
or `routine-more` files are rejected rather than treated as another catalog. Run `make check`
before review; it validates sources and translations, runs negative contract tests, and checks
that committed `dist/` is reproducible.

During development, `contentVersion` follows the tracked development version and the private
repository imports a reviewed `main` snapshot with `make sync-i18n-dev`; this does not create a
tag or claim that the version is online. The private `version-state.json` separately records the
published and development versions. Only the maintainer's explicit release operation creates
`i18n-vX.Y.Z` and lets the private Mod import that immutable tag with `make sync-i18n
I18N_VERSION=X.Y.Z`.
