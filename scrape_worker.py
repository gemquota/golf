"""Shared scrape worker primitives used by all scrape entry points."""
import csv
import datetime
import json
import random
import threading
import time
from pathlib import Path

import requests
from requests.exceptions import HTTPError

import config
import db
import network as net

RAW_DIR = Path("data/raw_responses")
TMP_DIR = Path("data")
DEBUG_DIR = Path("data/debug")
RECONCILIATION_CSV = Path("data/bonus_reconciliation.csv")
RECONCILIATION_LOCK = threading.Lock()


def record_bonus_reconciliation(url, merchant_name, raw_bonus_count, raw_promotion_count,
                                malformed_count, nonpositive_count, eligible_count,
                                inserted_count):
    """Persist per-site counts so missing records can be traced, not guessed at."""
    RECONCILIATION_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RECONCILIATION_LOCK:
        needs_header = not RECONCILIATION_CSV.exists() or RECONCILIATION_CSV.stat().st_size == 0
        with RECONCILIATION_CSV.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "timestamp", "url", "merchant_name", "raw_bonus_count",
                "raw_promotion_count", "raw_total", "malformed_count",
                "nonpositive_or_missing_amount_count", "eligible_count",
                "inserted_count", "matched_existing_count",
            ])
            if needs_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "url": url, "merchant_name": merchant_name,
                "raw_bonus_count": raw_bonus_count,
                "raw_promotion_count": raw_promotion_count,
                "raw_total": raw_bonus_count + raw_promotion_count,
                "malformed_count": malformed_count,
                "nonpositive_or_missing_amount_count": nonpositive_count,
                "eligible_count": eligible_count, "inserted_count": inserted_count,
                "matched_existing_count": eligible_count - inserted_count,
            })

ERROR_MAP = [
    ("MERCHANT", 201), ("Captcha", 202), ("gaierror", 102), ("Timeout", 104),
    ("Refused", 101), ("Connection", 103), ("403", 403),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def is_retryable_error(exception):
    """Retry only transient transport failures and explicitly retryable HTTP statuses."""
    if isinstance(exception, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exception, HTTPError):
        response = exception.response
        return bool(response is not None and response.status_code in (429, 500, 502, 503, 504))
    return False


def classify_error(exception):
    """Map an exception to a stable numeric error_code."""
    if isinstance(exception, net.AuthenticationError):
        return 304
    if isinstance(exception, HTTPError):
        return exception.response.status_code
    if isinstance(exception, requests.exceptions.Timeout):
        return 104

    # requests wraps several distinct transport failures in ConnectionError.
    # Test the specific cases before the broad superclass or they collapse to E103.
    if isinstance(exception, requests.exceptions.SSLError):
        return 105

    message = str(exception).lower()
    if (
        "nameresolutionerror" in message
        or "failed to resolve" in message
        or "getaddrinfo failed" in message
        or "temporary failure in name resolution" in message
        or "name or service not known" in message
    ):
        return 102
    if (
        isinstance(exception, ConnectionRefusedError)
        or "connection refused" in message
        or "errno 111" in message
    ):
        return 101
    if isinstance(exception, requests.exceptions.ConnectionError):
        return 103
    if isinstance(exception, ValueError):
        return 302
    error_string = str(exception)
    lowered_error = error_string.lower()
    for error_pattern, error_code in ERROR_MAP:
        if error_pattern.lower() in lowered_error:
            return error_code
    if "login" in error_string.lower():
        return 304
    return 301


def process_bonus(bonus, merchant_name, url, fingerprint, perceived_value, expiry, fuzzy=True):
    """Persist or mirror-match a bonus. Returns (bonus_uid, is_new)."""
    existing_records = db.execute(
        "SELECT bonus_uid, mirrors FROM bonuses WHERE fingerprint=?",
        (fingerprint,),
    )
    if existing_records:
        unique_id, mirrors = existing_records[0]
        if url not in str(mirrors):
            db.execute(
                "UPDATE bonuses SET mirrors=?, last_seen=CURRENT_TIMESTAMP WHERE bonus_uid=?",
                (f"{mirrors},{url}", unique_id),
            )
        return unique_id, 0

    if fuzzy:
        merchant_name_rows = db.execute(
            "SELECT name, bonus_uid, mirrors FROM bonuses WHERE merchant_name=?",
            (merchant_name,),
        )
        if merchant_name_rows:
            existing_names = [row[0] for row in merchant_name_rows if row[0]]
            matched_name = db.find_matching_name(bonus.get("name"), existing_names)
            if matched_name:
                matched_row = next((row for row in merchant_name_rows if row[0] == matched_name), None)
                if matched_row and url not in str(matched_row[2]):
                    db.execute(
                        "UPDATE bonuses SET mirrors=?, last_seen=CURRENT_TIMESTAMP WHERE bonus_uid=?",
                        (f"{matched_row[2]},{url}", matched_row[1]),
                    )
                return (matched_row[1] if matched_row else None), 0

    unique_id = f"{url}|{bonus.get('id')}"
    expiry_string = expiry.isoformat() if expiry else None
    db.execute(
        "REPLACE INTO bonuses(bonus_uid, external_id, url, amount, perceived_value, raw_json, "
        "expiry, fingerprint, mirrors, last_seen, merchant_name, name) "
        "VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?)",
        (
            unique_id, bonus.get("id"), url, str(bonus.get("amount", 0)), perceived_value,
            json.dumps(bonus), expiry_string, fingerprint, url, merchant_name, bonus.get("name"),
        ),
    )
    return unique_id, 1


def try_scrape(scraper_session, url, username, password, record_raw=False, chunk_id=0, write_csv=True):
    """Scrape one URL: page → login/session → sync → persist bonuses.

    Returns (success, html_content, site_bonuses, site_new).
    """
    page_response = net.get_page_response(scraper_session, url)
    html_content = page_response.text
    try:
        merchant_id, merchant_name = net.parse_merchant_info(html_content)
    except ValueError as exc:
        # Keep response metadata on the exception so the caller can diagnose
        # templates/redirects without dumping potentially sensitive page HTML.
        raise net.MerchantPageError(exc, page_response) from exc
    db.execute("UPDATE sites SET merchant_name=? WHERE url=?", (merchant_name, url))
    api_url = net.build_api_url(url)

    session_data = db.load_session(url, username)
    user_data = None
    if session_data:
        try:
            timestamp = datetime.datetime.fromisoformat(session_data["ts"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
            if (datetime.datetime.now(datetime.timezone.utc) - timestamp.astimezone(datetime.timezone.utc)).total_seconds() < 21600:
                scraper_session.cookies.update(session_data["ck"])
                user_data = session_data["data"]
        except Exception:
            pass

    if not user_data:
        user_data = net.login(scraper_session, api_url, username, password, merchant_id)
        db.save_session(url, username, scraper_session.cookies.get_dict(), user_data)

    try:
        sync_response = net.sync_user_data(
            scraper_session, api_url, merchant_id, user_data.get("token"), user_data.get("id"),
        )
    except Exception:
        user_data = net.login(scraper_session, api_url, username, password, merchant_id)
        db.save_session(url, username, scraper_session.cookies.get_dict(), user_data)
        sync_response = net.sync_user_data(
            scraper_session, api_url, merchant_id, user_data.get("token"), user_data.get("id"),
        )

    if record_raw:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        timestamp_string = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_url = url.replace("https://", "").replace("/", "_")
        (RAW_DIR / f"{timestamp_string}_{safe_url}.json").write_text(json.dumps(sync_response, indent=2))

    # Validate the response envelope. A malformed/truncated payload must not be
    # reported as a successful zero-bonus scrape.
    if not isinstance(sync_response, dict):
        raise ValueError("syncData response must be a JSON object")
    response_data = sync_response.get("data")
    if not isinstance(response_data, dict):
        raise ValueError("syncData response is missing its data object")
    raw_bonuses = response_data.get("bonus", [])
    raw_promotions = response_data.get("promotions", [])
    if not isinstance(raw_bonuses, list) or not isinstance(raw_promotions, list):
        raise ValueError("syncData bonus/promotions fields must be arrays")

    site_bonuses = 0
    site_new = 0
    malformed_count = 0
    nonpositive_count = 0
    csv_path = TMP_DIR / f"tmp_{chunk_id}.csv"

    for bonus in raw_bonuses + raw_promotions:
        if not isinstance(bonus, dict):
            malformed_count += 1
            continue
        normalized = {str(k).lower(): v for k, v in bonus.items()}
        amount = normalized.get("amount")
        if amount is None or db.float_value(amount) <= 0:
            nonpositive_count += 1
            continue
        site_bonuses += 1
        perceived_val = db.perceived_value(normalized)
        expiry = db.parse_expiry(str(normalized.get("name", "")) + str(normalized.get("claimcondition", "")))
        fingerprint = db.fingerprint_bonus(normalized)
        _uid, is_new = process_bonus(
            normalized, merchant_name, url, fingerprint, perceived_val, expiry, fuzzy=True,
        )
        site_new += is_new

        if write_csv:
            row_data = {k: normalized.get(k, normalized.get(k.upper(), "")) for k in db.HEADERS[:-2]}
            row_data["url"] = url
            row_data["mname"] = merchant_name
            row_data["perceived_value"] = perceived_val
            row_data["is_new"] = 1 if is_new else 0
            db.append_csv_row(row_data, str(csv_path))

    record_bonus_reconciliation(
        url, merchant_name, len(raw_bonuses), len(raw_promotions),
        malformed_count, nonpositive_count, site_bonuses, site_new,
    )
    return True, html_content, site_bonuses, site_new


def mark_site_result(url, error_code):
    db.execute(
        "UPDATE sites SET updated_at=CURRENT_TIMESTAMP, error_code=? WHERE url=?",
        (error_code, url),
    )


def ensure_site(url):
    db.execute("INSERT OR IGNORE INTO sites(url) VALUES (?)", (url,))
