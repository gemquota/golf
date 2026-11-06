# Terminal interface

`terminal.py` renders the scraper's interactive terminal interface with Rich and maintains short rolling windows of progress and performance information.

## Main responsibilities

- Render startup configuration and system status.
- Format per-site progress, error categories, streaks, and throughput.
- Render the final run summary.
- Forward progress events to the dashboard broadcaster.

The terminal interface is a presentation layer. It should not own scraper state or persistence.

See [terminal.py](../../terminal.py).
