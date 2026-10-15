# Third-Batch Roadmap Ideas

**Status:** Candidate proposals for user selection; not yet added to a phase roadmap and not implemented.
**Focus:** Extend the existing FastAPI + inline React dashboard, SQLite database, CSV export pipeline, and collected bonus/site data. These ideas complement the existing Phase 3 console/dashboard refinement list and the selected Phase 2 baseline trend charts and taxonomy; they avoid restating those features.

## Web dashboard and operator analysis

1. **Saved analysis workspaces (Medium)** — save named combinations of dashboard filters, selected merchants, time range, and visible measures; keep them separate from share-link state and personal favorite/hide preferences.
2. **Cross-view drill-through (Medium)** — selecting a site or chart interval opens the corresponding offers and source records with the active filters preserved.
3. **Run-versus-market context (Medium)** — present current scrape coverage and health alongside offer trends so users can distinguish a market change from a collection gap.
4. **Data freshness and coverage panel (Low)** — show last successful observation, stale-record counts, known collection gaps, and the timestamp basis for the current view.
5. **Analyst annotations (Medium)** — attach dated notes to a site, offer, or trend interval, with provenance and edit history, without mutating scraped source fields.

## Database, query, and data quality

6. **Versioned data dictionary (Low)** — document each stored/exported field, unit, null meaning, derivation, and schema version; generate a machine-readable field catalog for consumers.
7. **Historical observation ledger (High)** — store immutable, timestamped changes to offer fields so analysis can distinguish observed states from current-row first/last-seen approximations.
8. **Data-quality scoring and issue queue (Medium)** — identify suspicious or incomplete records (invalid dates, contradictory amounts, missing identity, implausible values) and expose explainable issues for review.
9. **Duplicate and entity-resolution review (High)** — propose likely duplicate offers/sites with matching evidence and confidence, while requiring explicit review before merging identities.
10. **Reusable query/filter API (Medium)** — provide a documented, bounded query interface for existing search, category, merchant, time, and quality filters with stable pagination and deterministic sort order.
11. **Database health and query diagnostics (Medium)** — report table/index size, slow query samples, WAL status, and export duration to guide indexing and maintenance from measurements.

## Interoperability and exports

12. **Versioned JSON export (Medium)** — complement the existing CSVs with a documented JSON format that preserves nested source fields and explicit nulls.
13. **Parquet or analytical columnar export (High)** — offer an optional columnar snapshot for efficient offline analysis, with schema metadata and reproducible generation.
14. **Incremental change feed (High)** — export additions, updates, and removals after a caller-provided cursor, with stable IDs and replay-safe ordering.
15. **OpenAPI-backed consumer contract (Medium)** — publish endpoint schemas, examples, pagination rules, error shapes, and compatibility policy from the FastAPI app.
16. **Import validation and preview (Medium)** — accept externally prepared annotations/classifications through a dry-run validator that reports row-level errors and proposed changes before applying them.
17. **Export profiles (Low)** — let operators select documented field sets and formats for viewer, audit, and analysis use cases while keeping current viewer CSV schemas stable.

## Trend analysis and extrapolation

18. **Cohort retention analysis (Medium)** — estimate how long offers remain observable by category or merchant, report cohort size and censoring, and avoid treating last observation as confirmed expiry.
19. **Seasonality and recurring-pattern analysis (High)** — detect recurring timing patterns in observed offer starts/ends, with minimum-sample and confidence requirements.
20. **Offer lifecycle funnel (Medium)** — quantify first observed → modified → last observed/expired transitions and distinguish missing observations from confirmed withdrawal.
21. **Coverage-adjusted trend estimates (High)** — show raw counts beside estimates adjusted for site scrape coverage and data freshness, with method and uncertainty clearly exposed.
22. **Merchant anomaly detection (High)** — flag unusual changes in offer count/value relative to a merchant's own baseline; provide the contributing records and avoid asserting causality.
23. **Scenario and forecast bands (High)** — offer conservative short-horizon projections only where history supports them, with backtests, uncertainty intervals, and an explicit non-prediction state for sparse data.
24. **Metric definition and sensitivity explorer (Medium)** — allow analysts to inspect how trend conclusions change under alternate expiry rules, stale-data thresholds, and value measures.

## Suggested sequencing principles

- Land field definitions, stable identifiers, and schema/version contracts before expanding exports or exposing a general query API.
- Prefer additive, reproducible exports before a change feed; design both around stable IDs and explicit timestamps.
- Establish trustworthy observation history and coverage/freshness metrics before retention, seasonality, adjusted trends, anomalies, or forecasts.
- Keep extrapolations descriptive and uncertainty-aware: distinguish observed facts, derived metrics, and estimates in the UI and exported data.
- Treat merge/import actions as reviewable proposals; do not silently rewrite historical source records.
