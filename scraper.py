import csv, datetime, json, random, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import config, db, server
from account_scheduler import partition_urls_by_account
from state_persistence import atomic_write_json
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
ERROR_REPORT_LOCK = threading.Lock()
SITE_ERRORS_CSV = Path("data/site_errors.csv")
CAPTCHA_QUEUE = Path("data/captcha_required.txt")

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
    atomic_write_json(ACCOUNT_STATE, data)


def record_site_error(url, account_id, error_code, exception):
    """Append non-authentication failures to a durable report and CAPTCHA queue."""
    if error_code == 304:
        return
    labels = {
        101: "connection_refused",
        102: "dns_error",
        103: "connection_error",
        104: "timeout",
        201: "merchant_error",
        202: "captcha_required",
        301: "unknown_error",
        302: "invalid_response",
        403: "http_forbidden",
    }
    category = labels.get(error_code, f"http_{error_code}" if 400 <= error_code < 600 else "other_error")
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    message = " ".join(str(exception).split())[:1000]
    with ERROR_REPORT_LOCK:
        SITE_ERRORS_CSV.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not SITE_ERRORS_CSV.exists() or SITE_ERRORS_CSV.stat().st_size == 0
        with SITE_ERRORS_CSV.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "timestamp", "url", "account_id", "error_code", "category", "message"
            ])
            if needs_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": checked_at, "url": url, "account_id": account_id,
                "error_code": error_code, "category": category, "message": message,
            })

        # Keep this manual-review queue until the user removes a checked URL.
        # A later CAPTCHA failure adds the URL again.
        if error_code == 202:
            CAPTCHA_QUEUE.parent.mkdir(parents=True, exist_ok=True)
            existing = set(
                line.strip() for line in CAPTCHA_QUEUE.read_text(encoding="utf-8").splitlines()
            ) if CAPTCHA_QUEUE.exists() else set()
            if url not in existing:
                with CAPTCHA_QUEUE.open("a", encoding="utf-8") as stream:
                    stream.write(url + "\n")


def record_account_success(url, account_id):
    """Persist the successful account and its verified registration state."""
    verified_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with ACCOUNT_SUCCESS_LOCK:
        ACCOUNT_SUCCESS.parent.mkdir(parents=True, exist_ok=True)
        successes = _load_json_mapping(ACCOUNT_SUCCESS)
        successes[url] = account_id
        atomic_write_json(ACCOUNT_SUCCESS, successes)
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
    """Run one worker batch and always release its HTTP session."""
    session = net.create_session(random.choice(proxy_pool) if proxy_pool else None)
    try:
        return _worker_tasks(
            session, chunk_id, stats, stats_lock, total_tasks, ip_score,
            record_raw, worker_count, tasks, proxy_pool, on_update,
        )
    finally:
        session.close()


def _worker_tasks(scraper_session, chunk_id, stats, stats_lock, total_tasks, ip_score, record_raw, worker_count, tasks, proxy_pool, on_update):
    current_ua_index = 0

    for sequence, batch_position, url, username, password, account_id in tasks:
        if server.STOPPED:
            break
        while server.PAUSED and not server.STOPPED:
            time.sleep(0.5)
        if server.STOPPED:
            break

        current_index = sequence

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
                    record_site_error(url, account_id, error_code, exception)
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
                    "batch_index": batch_position,
                    "worker_number": chunk_id + 1,
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
                "batch_index": batch_position,
                "worker_number": chunk_id + 1,
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

def _run_scrape(on_update=None, on_launcher=None, on_completion=None):
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

    next_attempt_sequence = 0

    def process_url_batch(current_url_list, account_index=0):
        if not current_url_list:
            return
        username, password = account_list[account_index]
        account_id = f"U{account_index + 1}"
        nonlocal next_attempt_sequence
        task_list = []
        for batch_position, url in enumerate(current_url_list, start=1):
            next_attempt_sequence += 1
            task_list.append((next_attempt_sequence, batch_position, url, username, password, account_id))
        max_workers = max(1, config.config_parser.getint("SETTINGS", "workers", fallback=10))
        num_workers = min(max_workers, len(task_list))
        task_chunks = [task_list[i::num_workers] for i in range(num_workers)]

        if server.STOPPED:
            return
        # Workers finish concurrently; emit their results in task order.
        pending_updates = {}
        next_display_position = [1]
        display_lock = threading.Lock()

        def ordered_update(data):
            if not on_update:
                return
            position = data.get("batch_index")
            with display_lock:
                pending_updates[position] = data
                while next_display_position[0] in pending_updates:
                    ready = pending_updates.pop(next_display_position[0])
                    next_display_position[0] += 1
                    on_update(ready)

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(
                    worker, i, execution_stats, thread_locks, len(task_list),
                    ip_score, record_raw_responses, num_workers, task_chunks[i],
                    proxy_list, ordered_update if on_update else None
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

    # Honour verified URL/account associations before discovery. Unknown URLs
    # start with U1; known URLs start with the account that last succeeded.
    known_successes = load_account_successes()
    original_known_by_account, unknown_urls = partition_urls_by_account(
        url_list, known_successes, len(account_list)
    )

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
            attempted_codes[url].append(current_error_code(url))

    # Process each known account cohort first. Cohort order and URL order are
    # shuffled, but each URL is always assigned to its verified account first.
    known_account_order = list(original_known_by_account)
    random.shuffle(known_account_order)
    for account_index in known_account_order:
        if server.STOPPED:
            break
        run_account_batch(original_known_by_account[account_index], account_index)

    # Unknown URLs use the primary account for discovery.
    if not server.STOPPED:
        run_account_batch(unknown_urls, 0)

    # Only explicit E304 authentication rejections permit account rotation.
    # Network failures, timeouts, CAPTCHA and merchant errors never trigger it.
    for account_index in range(len(account_list)):
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

    if SITE_ERRORS_CSV.exists():
        with SITE_ERRORS_CSV.open(newline="", encoding="utf-8") as stream:
            error_count = max(0, sum(1 for _ in stream) - 1)
        print(f"Non-authentication error report: {SITE_ERRORS_CSV} ({error_count} recorded events)")
    if CAPTCHA_QUEUE.exists():
        captcha_count = sum(1 for line in CAPTCHA_QUEUE.read_text(encoding="utf-8").splitlines() if line.strip())
        print(f"Manual CAPTCHA review queue: {CAPTCHA_QUEUE} ({captcha_count} sites pending)")

    server.IS_RUNNING = False
    if on_completion:
        on_completion(execution_stats)
    return final_csv_path


def run_scrape(on_update=None, on_launcher=None, on_completion=None):
    """Run a scrape while guaranteeing process state and worker temp cleanup."""
    server.IS_RUNNING = True
    try:
        return _run_scrape(on_update, on_launcher, on_completion)
    except BaseException:
        for temporary in TMP_DIR.glob("tmp_*.csv"):
            try:
                temporary.unlink()
            except OSError:
                pass
        raise
    finally:
        server.IS_RUNNING = False
