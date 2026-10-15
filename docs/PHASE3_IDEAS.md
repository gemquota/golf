# Phase 3 Ideas — Current-Implementation Refinement

**Status:** Candidate ideas only; not committed to a roadmap or implementation plan.
**Focus:** Improve the existing Rich console output and the current FastAPI/inline-React dashboard without replacing either.

## Console output

1. **Readable compact mode (Low)** — retain one-line-per-site output but show a smaller, configurable set of metrics; move secondary metrics to verbose mode.
2. **Aligned fixed-width columns (Low)** — use a consistent column layout with truncation/ellipsis for long URLs and predictable numeric widths.
3. **Meaningful status abbreviations with legend (Low)** — use distinct concise states for success, timeout, blocked, redirect, parse failure, and skipped; keep their meaning discoverable.
4. **Terminal-width-aware layout (Medium)** — adapt line content to terminal width and avoid wrapped lines that become visually detached from their site result.
5. **Separate live progress from diagnostic detail (Medium)** — keep the default progress stream scannable; put retries, account attempts, and exception context behind verbose/debug output or a per-site follow-up line.
6. **Stable progress semantics (Medium)** — label task ordinal, completion sequence, and elapsed/ETA distinctly; show whether ETA is approximate and avoid implying completion order is input order.
7. **Accessible/plain output mode (Low)** — provide a no-color/no-emoji mode suitable for logs, screen readers, and narrow or non-interactive terminals.
8. **Completion summary with actionable failure sample (Medium)** — preserve aggregate counts and add a bounded list of representative failure reasons and next diagnostic steps.

## Existing web dashboard

9. **Reconnect with current-state snapshot (Medium)** — after WebSocket loss, reconnect with backoff and restore the latest run state before appending events.
10. **Live Activity controls (Low)** — filter recent events by success/failure, search by hostname, and select a visible row limit.
11. **Better dense activity rows (Low)** — show a stable sequence number, compact status badge, elapsed time, and expand-on-demand details instead of overloading the main row.
12. **Dashboard layout persistence (Low)** — remember collapsed sections and chosen activity density in browser storage.
13. **Responsive site-review table (Medium)** — turn wide rows into stacked cards on narrow screens while preserving every review action and field.
14. **Clear async feedback (Low)** — show saving/loading states, disable duplicate submissions, and display specific API errors inline rather than relying on console logging.
15. **Settings validation and dirty-state handling (Medium)** — validate numeric ranges inline, mark unsaved changes, and make save failures visible without closing the dialog.
16. **Run lifecycle clarity (Medium)** — consistently distinguish idle, starting, running, paused, stopping, stopped, and completed states, including the zero-site case.
17. **Progress-focused overview (Medium)** — add a clear progress bar, current site, counts, and ETA with graceful handling of missing/stale data.
18. **Dashboard smoke-test harness (High)** — exercise auth, settings save, pause/resume/stop, review edits, and WebSocket disconnect behavior against a local mocked API.

## Candidate order

Start with low-risk readability and feedback improvements (1–3, 7, 10–12, 14), then responsive layout and lifecycle semantics (4–6, 13, 15–17), and consider reconnect and end-to-end harness work (9, 18) after the event/state contracts are stable. These are suggestions, not required sequencing.
