import csv, datetime, json, random, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import config, db, server
import network as net
from scrape_worker import (
    USER_AGENTS,
    classify_error,
    ensure_site,
    mark_site_result,
    process_bonus,
    try_scrape,
)

RAW_DIR = Path("data/raw_responses")
TMP_DIR = Path("data")
DEBUG_DIR = Path("data/debug")
ACCOUNT_SUCCESS = Path("data/account_success.json")
ACCOUNT_STATE = Path("data/account_state.json")
ACCOUNT_SUCCESS_LOCK = threading.Lock()

# Back-compat aliases for callers/tests that imported these from scraper.
try_scrape_url = try_scrape


def _load_json_mapping(path):
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_account_successes():
    """Load legacy URL -> U# success mappings without exposing account credentials."""
    with ACCOUNT_SUCCESS_LOCK:
        return _load_json_mapping(ACCOUNT_SUCCESS)


def _save_account_state_locked(data):
    ACCOUNT_STATE.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_STATE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def record_account_success(url, account_id):
    """Persist the successful account and its verified registration state."""
    verified_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with ACCOUNT_SUCCESS_LOCK:
        ACCOUNT_SUCCESS.parent.mkdir(parents=True, exist_ok=True)
        successes = _load_json_mapping(ACCOUNT_SUCCESS)
        successes[url] = account_id
        ACCOUNT_SUCCESS.write_text(json.dumps(successes, indent=2, sort_keys=True) + "\n")
        state = _load_json_mapping(ACCOUNT_STATE)
        state[url] = {
            "status": "registered",
            "account_id": account_id,
            "verified_at": verified_at,
            "last_attempt_at": verified_at,
            "last_error_code": None
        }
        _save_account_state_locked(state)


def record_account_discovery_result(url, attempted_codes):
    """Record an unsuccessful account discovery without mistaking outages for non-registration."""
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    conclusive_failures = bool(attempted_codes) and all(code == 304 for code in attempted_codes)
    with ACCOUNT_SUCCESS_LOCK:
        state = _load_json_mapping(ACCOUNT_STATE)
        previous = state.get(url, {})
        # A previous confirmed association is not erased by a transient failed scrape.
        if previous.get("status") == "registered" and previous.get("account_id"):
            previous["last_attempt_at"] = checked_at
            previous["last_error_code"] = attempted_codes[-1] if attempted_codes else None
            state[url] = previous
        else:
            state[url] = {
                "status": "unregistered" if conclusive_failures else "unknown",
                "account_id": None,
                "verified_at": checked_at if conclusive_failures else None,
                "last_attempt_at": checked_at,
                "attempted_error_codes": attempted_codes
            }
        _save_account_state_locked(state)

def worker(chunk_id, stats, stats_lock, total_tasks, ip_score, record_raw, worker_count, tasks, proxy_pool, on_update):
    scraper_session = net.create_session(random.choice(proxy_pool) if proxy_pool else None)
    current_ua_index = 0

    for url, username, password, account_id in tasks:
        if server.STOPPED:
            break
        while server.PAUSED and not server.STOPPED:
            time.sleep(0.5)
        if server.STOPPED:
            break

        with stats_lock["index"]:
            stats["index"] += 1
            current_index = stats["index"]

        ensure_site(url)
        start_time = time.perf_counter()
        time.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY))

        html_content = ""
        success = False
        error_code = 0
        exception = None
        site_bonuses = 0
        site_new = 0
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    current_ua_index = (current_ua_index + 1) % len(USER_AGENTS)
                    scraper_session.headers.update({"User-Agent": USER_AGENTS[current_ua_index]})
                    scraper_session.timeout = config.TIMEOUT + (attempt * 10)
                    time.sleep(random.uniform(2.0, 4.0) * attempt)

                success, html_content, site_bonuses, site_new = try_scrape(
                    scraper_session, url, username, password,
                    record_raw=record_raw, chunk_id=chunk_id, write_csv=True,
                )
                break

            except Exception as exc:
                exception = exc
                if attempt == max_retries - 1:
                    error_code = classify_error(exception)
                    mark_site_result(url, error_code)
                    with stats_lock["stats"]:
                        stats["failures"] += 1

                    if error_code in (201, 202, 302):
                        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        safe_url = url.replace("https://", "").replace("/", "_")
                        timestamp_string = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        if html_content:
                            (DEBUG_DIR / f"E{error_code}_{timestamp_string}_{safe_url}.html").write_text(html_content)

                    db.log_event(f"E{error_code}", url, str(exception))
                else:
                    continue

        if success:
            record_account_success(url, account_id)
            with stats_lock["stats"]:
                stats["total_bonuses"] += site_bonuses
                stats["successes"] += 1
                stats["new_bonuses"] += site_new

            mark_site_result(url, 200)

            if on_update:
                on_update({
                    "index": current_index,
                    "successes": stats["successes"],
                    "failures": stats["failures"],
                    "total_bonuses": stats["total_bonuses"],
                    "site_url": url,
                    "account_username": username,
                    "status_message": "DONE",
                    "site_bonuses_gt_zero": site_bonuses,
                    "N": total_tasks,
                    "elapsed": time.perf_counter() - start_time,
                    "ip_score": ip_score,
                    "site_new_bonuses": site_new,
                    "total_new_bonuses": stats["new_bonuses"],
                    "nw": worker_count
                })
        elif on_update:
            on_update({
                "index": current_index,
                "successes": stats["successes"],
                "failures": stats["failures"],
                "total_bonuses": stats["total_bonuses"],
                "site_url": url,
                "account_username": username,
                "status_message": f"E{error_code}" if error_code else "FAIL",
                "site_bonuses_gt_zero": 0,
                "N": total_tasks,
                "elapsed": time.perf_counter() - start_time,
                "ip_score": ip_score,
                "error_details": str(exception),
                "total_new_bonuses": stats["new_bonuses"],
                "nw": worker_count
            })

def run_scrape(on_update=None, on_launcher=None, on_completion=None):
    resume_mode = "-r" in sys.argv
    shuffle_mode = "-s" in sys.argv
    verbose_index = sys.argv.index("-v") if "-v" in sys.argv else -1
    record_raw_responses = verbose_index >= 0 and verbose_index + 1 < len(sys.argv) and sys.argv[verbose_index + 1] == "max"

    url_list, account_list = config.parse_urls_and_accounts(shuffle_mode)
    execution_stats = {"index": 0, "successes": 0, "failures": 0, "total_bonuses": 0, "new_bonuses": 0}
    if resume_mode:
        # datetime(), unlike date(), enforces a true rolling 24-hour window.
        completed_urls = {
            row[0]
            for row in db.execute(
                "SELECT url FROM sites WHERE updated_at > datetime('now','-1 day') AND error_code=200"
            )
        }
        url_list = [url for url in url_list if url not in completed_urls]

    if not url_list or not account_list:
        server.IS_RUNNING = False
        if on_completion:
            on_completion(execution_stats)
        return
    thread_locks = {"index": threading.Lock(), "stats": threading.Lock()}
    ip_score, _ = net.check_ip_reputation(config.ABUSEIPDB_KEY)
    proxy_list = config.load_proxies()

    run_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    final_csv_path = TMP_DIR / f"bonuses_{run_timestamp}.csv"
    db._init_csv(str(final_csv_path))

    def process_url_batch(current_url_list, account_index=0):
        if not current_url_list:
            return
        username, password = account_list[account_index]
        account_id = f"U{account_index + 1}"
        task_list = [(url, username, password, account_id) for url in current_url_list]
        max_workers = max(1, config.config_parser.getint("SETTINGS", "workers", fallback=10))
        num_workers = min(max_workers, len(task_list))
        task_chunks = [task_list[i::num_workers] for i in range(num_workers)]

        if server.STOPPED:
            return
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(
                    worker, i, execution_stats, thread_locks, len(task_list),
                    ip_score, record_raw_responses, num_workers, task_chunks[i],
                    proxy_list, on_update
                )
                for i in range(num_workers)
            ]
            for future in futures:
                future.result()

        for i in range(num_workers):
            temp_file_path = TMP_DIR / f"tmp_{i}.csv"
            if temp_file_path.exists():
                with temp_file_path.open(newline="") as csv_file:
                    for csv_row in csv.DictReader(csv_file, fieldnames=db.HEADERS):
                        db.append_csv_row(csv_row, str(final_csv_path))
                temp_file_path.unlink()

    if on_launcher:
        max_configured_workers = config.config_parser.getint("SETTINGS", "workers", fallback=10)
        on_launcher(len(url_list), len(proxy_list), min(max_configured_workers, len(url_list)), shuffle_mode, ip_score)

    # The configured accounts belong to this authorised site family. Run the
    # primary account across the full eligible list first, then honour known
    # URL/account associations, then rotate remaining authentication failures.
    known_successes = load_account_successes()
    original_known_by_account = {index: [] for index in range(len(account_list))}
    for url in url_list:
        account_id = known_successes.get(url)
        try:
            account_index = int(str(account_id)[1:]) - 1 if str(account_id).startswith("U") else -1
        except (TypeError, ValueError):
            account_index = -1
        if 0 <= account_index < len(account_list):
            original_known_by_account[account_index].append(url)

    # Track attempts per URL so fallback never repeats an account already tried.
    attempted_accounts = {url: set() for url in url_list}
    attempted_codes = {url: [] for url in url_list}

    def current_error_code(url):
        rows = db.execute("SELECT error_code FROM sites WHERE url=?", (url,))
        return rows[0][0] if rows else None

    def run_account_batch(urls, account_index):
        pending = [url for url in urls if url in attempted_accounts and
                   current_error_code(url) != 200 and
                   account_index not in attempted_accounts[url]]
        if not pending or server.STOPPED:
            return
        random.shuffle(pending)
        for url in pending:
            attempted_accounts[url].add(account_index)
        process_url_batch(pending, account_index)
        for url in pending:
            code = current_error_code(url)
            attempted_codes[url].append(code)
            if code == 200:
                continue

    # Pass 1: U1 gets the entire eligible URL list, in randomized order.
    primary_urls = list(url_list)
    random.shuffle(primary_urls)
    run_account_batch(primary_urls, 0)

    # Pass 2: process previously verified sites with their associated U2, U3,
    # etc. in deterministic account order. Successful U1 results are skipped.
    for account_index in range(1, len(account_list)):
        if server.STOPPED:
            break
        run_account_batch(original_known_by_account[account_index], account_index)

    # Pass 3: only conclusive authentication rejections enter fallback. A
    # timeout, outage, HTTP error or CAPTCHA is not evidence that credentials
    # are invalid, so those URLs remain untouched by account rotation.
    for account_index in range(1, len(account_list)):
        if server.STOPPED:
            break
        fallback_urls = [
            url for url in url_list
            if current_error_code(url) == 304
            and account_index not in attempted_accounts[url]
        ]
        run_account_batch(fallback_urls, account_index)

    # Persist the aggregate discovery outcome. A URL is labelled unregistered
    # only when every attempted account produced the explicit E304 rejection.
    for url in url_list:
        if attempted_codes[url] and current_error_code(url) != 200:
            record_account_discovery_result(url, attempted_codes[url])

    server.IS_RUNNING = False
    if on_completion:
        on_completion(execution_stats)
