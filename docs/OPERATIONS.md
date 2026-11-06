# Operations and reliability

## Scrape scheduling

A normal scrape considers every configured URL, including URLs whose database row records a previous success. Only `--resume` applies the rolling 24-hour successful-scrape exclusion. This distinction is intentional: historical success is not proof that the current invocation attempted a URL.

Account affinity is keyed by the exact configuration section (`U1`, `U2`, ...), not by the position of a filtered credential list. A missing `U1` therefore cannot silently turn `U2` into `U1`.

A known URL is attempted with its last verified account first. Unknown URLs start with the first configured account. Account fallback is permitted only after an explicit authentication rejection (E304); timeouts, connection failures, merchant errors, and CAPTCHA responses are not credential evidence.

## Retry behavior

Retries should be limited to transient transport failures and retryable server responses. Authentication rejection, CAPTCHA, malformed merchant responses, and ordinary client errors should be surfaced without cycling credentials. Keep retry counts bounded and use backoff to avoid amplifying an outage.

## Pipeline and exit status

The full CLI scrape includes maintenance, export generation, and optional publication. A failure in a required post-scrape stage must be visible as a non-zero process exit so shell scripts and scheduled workflows do not report a false success. Use `--no-pipeline` only when intentionally running scrape-only mode.

## Telemetry

Terminal counters, rolling success windows, streaks, and elapsed-time baselines are per invocation. Do not interpret aggregate SQLite history as current-run throughput.

## Validation boundaries

Unit tests and CI validate deterministic behavior using fixtures. They do not prove live merchant compatibility, current account credentials, proxy availability, or successful publication to an external hosting provider. Validate those separately in a controlled run.
