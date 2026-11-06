"""Deterministic account-affinity partitioning for scrape scheduling."""


def partition_urls_by_account(urls, known_successes, account_count, account_ids=None):
    """Return known cohorts and unknown URLs using stable configured account IDs."""
    cohorts = {index: [] for index in range(account_count)}
    account_indexes = {str(value): index for index, value in enumerate(account_ids)} if account_ids is not None else None
    unknown = []
    for url in urls:
        account_id = known_successes.get(url)
        if account_indexes is not None:
            account_index = account_indexes.get(str(account_id), -1)
        else:
            try:
                account_index = int(str(account_id)[1:]) - 1 if str(account_id).startswith("U") else -1
            except (TypeError, ValueError):
                account_index = -1
        if 0 <= account_index < account_count:
            cohorts[account_index].append(url)
        else:
            unknown.append(url)
    return cohorts, unknown
