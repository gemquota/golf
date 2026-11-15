# Repository documentation status

## Current documentation

- `docs/ARCHITECTURE.md`: module boundaries, runtime flow, and export ownership.
- `docs/api/`: maintained module and pipeline references.
- `docs/api/export_csv.md`: shared normalization, scoring context, and common CSV exports.
- `docs/api/export_viewer_data.md`: active viewer snapshot formats and adapter boundary.
- `docs/api/bonus_scoring.md`: scoring formula contract and confidence semantics.

## Maintenance policy

API documentation describes responsibilities and stable interfaces rather than
brittle source line numbers or synthetic complexity counts. Update the
relevant page whenever a module's responsibility or public data contract
changes. Exact implementation details and signatures remain defined by the
source.
