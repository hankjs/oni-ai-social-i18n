# oni-ai-social-i18n

Public catalog for ONI Social Life player-visible strings.

- Source locale: `zh`
- Published locales: `zh`, `en`
- Edit `catalog/` and `locales/`; never hand-edit `dist/`
- `python3 tools/export.py` regenerates `dist/`
- `python3 tools/validate.py` checks uniqueness, tokens, and dialogue structure

Release tags are `i18n-vX.Y.Z` and must match `manifest.json` `contentVersion`.
The private Mod imports a tag with `make sync-i18n I18N_VERSION=X.Y.Z`.
