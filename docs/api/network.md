# Network API

`network.py` owns HTTP session creation, request helpers, merchant metadata parsing, authentication, and IP-reputation lookup.

## Main responsibilities

- Create a browser-like HTTP session and apply configured proxy routing.
- Fetch merchant pages and construct API requests.
- Parse merchant identifiers and names from page content.
- Authenticate accounts and synchronize user data.
- Classify explicit authentication rejection separately from other HTTP failures.
- Cache IP-reputation results locally.

Keep retry policy and scrape orchestration in the caller. Never disable TLS certificate verification to work around a site-specific failure.

See [network.py](../../network.py).
