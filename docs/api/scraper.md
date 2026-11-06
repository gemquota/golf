# Scraper API

`scraper.py` coordinates scraping work and delegates HTTP/session operations to `network.py`, persistence to `db.py`, configuration to `config.py`, and progress reporting to `terminal.py` and `server.py`.

## Main responsibilities

- Classify network and application errors.
- Normalize and persist discovered bonus records.
- Execute site/account tasks across worker threads.
- Aggregate run statistics and expose progress events.

The scraper is the orchestration layer. Keep transport details in `network.py`, durable state in `db.py`, and user-interface concerns out of worker logic.

See [scraper.py](../../scraper.py).
