# Golf bonus scraper

Golf is a Python scraper and local dashboard for collecting merchant bonus offers, tracking account-to-site affinity, maintaining URL health, and publishing CSV-backed viewer data.

## Quick start

Requires Python 3.10+ and the packages in `requirements.txt`.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp in/meta/config.ini.example in/config/config.ini
# Add merchant URLs to in/config/urls.txt and credentials to local config.
python -m golf migrate
python -m golf scrape --no-publish
```

Keep credentials in environment variables or the ignored local configuration file. Account sections use stable IDs such as `[U1]`, `[U2]`; missing credentials do not renumber the remaining accounts.

## Commands

| Command | Purpose |
| --- | --- |
| `python -m golf scrape` | Scrape, maintain site state, build exports, publish viewer data |
| `python -m golf scrape --no-pipeline` | Scrape only |
| `python -m golf scrape -r` | Skip URLs successfully scraped in the rolling last 24 hours |
| `python -m golf interactive` | Start the terminal UI and local dashboard |
| `python -m golf pipeline --no-publish` | Run maintenance and local exports |
| `python -m golf export --viewer` | Rebuild viewer exports |
| `python -m golf migrate` | Apply the idempotent SQLite migration |
| `python export_sites.py` | Export registered URLs grouped and sorted by merchant ID |

## Runtime state

SQLite lives at `data/base.db`. Local account affinity and run state are stored under `data/`; local configuration belongs in `in/config/config.local.ini` or environment variables. Do not commit credentials, live session data, or generated runtime state.

## Tests

Run the network-free suite with:

```sh
python -m unittest discover -s tests -v
```

The suite uses fixtures and mocks; it does not validate live merchant availability or credential validity.
