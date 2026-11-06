"""Deterministic account-affinity partitioning for scrape scheduling."""


def partition_urls_by_account(urls, known_successes, account_count):
    """Return (known cohorts, unknown URLs), ignoring invalid/stale account IDs."""
    cohorts = {index: [] for index in range(account_count)}
    unknown = []
    for url in urls:
        account_id = known_successes.get(url)
        try:
            account_index = int(str(account_id)[1:]) - 1 if str(account_id).startswith("U") else -1
        except (TypeError, ValueError):
            account_index = -1
        if 0 <= account_index < account_count:
            cohorts[account_index].append(url)
        else:
            unknown.append(url)
    return cohorts, unknown
