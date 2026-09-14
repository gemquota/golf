#!/usr/bin/env python3
"""Diagnose why sites are failing on this device.

Compares plain requests vs cloudscraper, then runs one FULL scrape
(login + bonus API) with real credentials and full tracebacks.
Usage: python3 diag.py [url]   (defaults to in/config/test_url.txt)
"""
import sys
import traceback
from pathlib import Path

URL = sys.argv[1] if len(sys.argv) > 1 else Path("in/config/test_url.txt").read_text().strip()

print(f"python : {sys.version.split()[0]}")
print(f"target : {URL}\n")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- Step 1: transport check ---
print("1) cloudscraper GET:")
try:
    import cloudscraper
    session = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    session.headers.update(HEADERS)
    resp = session.get(URL, timeout=20)
    print(f"   HTTP {resp.status_code}, {len(resp.text)} bytes")
except Exception:
    print("   FAILED:")
    traceback.print_exc()
    sys.exit(1)

# --- Step 2: parse merchant info ---
print("2) parse merchant info:")
try:
    import network
    merchant_id, merchant_name = network.parse_merchant_info(resp.text)
    print(f"   id={merchant_id} name={merchant_name}")
except Exception:
    print("   FAILED:")
    traceback.print_exc()
    sys.exit(1)

# --- Step 3: full scrape with real account ---
print("3) full scrape (login + syncData):")
try:
    import config, scraper
    _, accounts = config.parse_urls_and_accounts(shuffle=False)
    if not accounts:
        print("   NO ACCOUNTS FOUND in in/config/config.ini ([U1]-[U5] sections)")
        sys.exit(1)
    user, pwd = accounts[0]
    print(f"   using account: {user[:3]}***")
    result = scraper.try_scrape_url(
        session, URL.rstrip("/"), user, pwd, record_raw=False, chunk_id=0
    )
    ok = result[0] if isinstance(result, tuple) else result
    print(f"   result: {'SUCCESS' if ok else 'FAILED'}")
    if ok:
        print("\nVERDICT: pipeline fully works - failures during bulk runs are")
        print("per-site issues or rate limiting, not setup.")
    else:
        print("\nVERDICT: scrape step returns failure - likely login rejected.")
        print("Check the account credentials against this site.")
except SystemExit:
    raise
except Exception:
    print("   CRASHED:")
    traceback.print_exc()
    print("\nVERDICT: exception above is the root cause - send this output back.")
