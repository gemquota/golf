# Daily scraping and commission release history

## What runs each day

The scheduled GitHub Actions workflow runs at **02:17 Australia/Brisbane time** (16:17 UTC). It:

1. Runs the scraper in headless mode against the URLs configured in `in/config/urls.txt`.
2. Exports the current bonus data for the existing viewer.
3. Compares each successfully scraped site's current bonuses with that site's last successful observation.
4. Records new bonuses, new commissions, changed terms/amounts, and bonuses no longer observed.
5. Rebuilds weekday statistics and site-level commission release patterns.
6. Commits the updated viewer CSVs and `viewer/public/bonus-history.json` to `main`, which triggers the Pages deployment workflow.

A failed scrape does **not** make a site's bonuses appear withdrawn. The comparison is updated only after a successful scrape for that site.

## Configure the scheduled runner

The workflow intentionally refuses to scrape until the private account configuration is supplied as a GitHub Actions secret.

1. Rotate any account credentials that were previously committed to the repository. Replacing the current file does not erase old commits from Git history.
2. Open the repository's **Settings → Secrets and variables → Actions**.
3. Create repository secret **`GOLF_CONFIG_INI`** containing the complete private INI configuration with the `SETTINGS` and `U1`, `U2`, etc. sections.
4. Optionally add **`GOLF_ABUSEIPDB_KEY`** if the IP reputation lookup is used.
5. Open **Actions → Daily bonus scrape and release tracking → Run workflow** to test it manually.

The secret is written to the runner's temporary checkout and is not committed by the workflow. Do not paste the private INI into issues, pull requests, logs, or source files. The workflow can run without the optional AbuseIPDB key.

## Local development

Keep real credentials in the ignored file `in/config/config.local.ini`. The tracked `in/config/config.ini` is now a safe template. The local file can use this shape:

```ini
[SETTINGS]
workers = 10
min_delay = 2.0
max_delay = 5.6
ui_user = admin
ui_pass =

[U1]
u = YOUR_ACCOUNT_USERNAME
p = YOUR_ACCOUNT_PASSWORD

[U2]
u = YOUR_SECOND_ACCOUNT_USERNAME
p = YOUR_SECOND_ACCOUNT_PASSWORD
```

The parser reads `config.local.ini` after the tracked template, so local values override it. Environment variables such as `GOLF_U1_USER` and `GOLF_U1_PASS` take precedence over INI values. Do not remove `in/config/config.local.ini` from `.gitignore`.

## Interpreting release-day results

The calendar distinguishes observation from certainty:

- **New commission:** a commission-like bonus appeared after a previous successful scrape of that site did not contain it.
- **Changed bonus:** a known bonus changed in one of the tracked fields.
- **No longer seen:** a bonus was absent from a later successful scrape. This is not proof the operator permanently removed it.
- **Likely weekday:** the weekday with the most observed new commission releases for that site.
- **Confidence:** low under three observed releases, moderate from three to seven, and higher from eight onward.

The initial successful scrape establishes a baseline. Bonuses already present on that first observation are not falsely counted as new releases. Patterns improve over time; the tracker cannot infer a release that appeared and disappeared entirely between daily checks, nor determine the exact publication time from once-daily observations.

The tracker retains up to 365 days of release events and run summaries, plus each site's latest successful baseline. The public JSON contains bonus observations and site URLs, not account credentials or session cookies.
