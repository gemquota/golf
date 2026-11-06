# Configuration API

`config.py` owns application configuration loading, URL/account parsing, proxy loading, and local settings persistence.

## Responsibilities

- Resolve configuration from the repository's configuration files and supported environment overrides.
- Parse configured account sections and site URLs for scraper workers.
- Normalize site URLs consistently before scraping.
- Load and persist dashboard settings through the configuration helpers.

## Operational notes

Keep secrets in local configuration or environment variables. Do not add credentials, session values, or proxy authentication to tracked examples or generated documentation.

See [config.py](../../config.py) and [the example configuration](../../in/meta/config.ini.example).
