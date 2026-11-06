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


## Reliability contract

- Every request uses the configured timeout and calls `raise_for_status()` before parsing response content.
- API helpers reject non-object JSON payloads with a clear `ValueError`, which is classified as an invalid response rather than a successful empty scrape.
- The AbuseIPDB cache is accepted only when its timestamp, score, and IP fields are valid and younger than one hour. Corrupt or expired entries are ignored.
- Cache writes use a temporary file and atomic replacement. A failed write cannot leave a partially written cache file.
- Parklogic redirect payloads are base64/JSON validated before use, and the redirected response is checked for HTTP errors.
