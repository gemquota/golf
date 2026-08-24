#!/usr/bin/env python3
"""Diagnose why sites are failing on this device.

Tests a single URL end-to-end with full tracebacks instead of error codes.
Usage: python3 diag.py [url]   (defaults to in/config/test_url.txt)
"""
import sys
import traceback
from pathlib import Path

import config

URL = sys.argv[1] if len(sys.argv) > 1 else Path("in/config/test_url.txt").read_text().strip()
USERNAME = config.config_parser.get("ACCOUNTS", "user1", fallback=None) or "unknown"
PASSWORD = config.config_parser.get("ACCOUNTS", "pass1", fallback=None) or "unknown"

print(f"python: {sys.version}")
print(f"testing: {URL}")

try:
    import network
    session = network.create_session()
    print("1. session created OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)

try:
    resp = session.get(URL, timeout=20)
    print(f"2. GET {URL} -> HTTP {resp.status_code}, {len(resp.text)} bytes")
except Exception:
    print("2. GET FAILED:")
    traceback.print_exc()
    sys.exit(1)

try:
    html = resp.text
    mid = html.find("MERCHANTID")
    mname = html.find("MERCHANTNAME")
    print(f"3. page markers: MERCHANTID found={mid != -1}, MERCHANTNAME found={mname != -1}")
except Exception:
    traceback.print_exc()

try:
    import scraper
    result = scraper.try_scrape_url(session, URL.rstrip("/"), USERNAME, PASSWORD, record_raw=False, chunk_id=0)
    print(f"4. try_scrape_url -> {result}")
    print("\nALL STEPS PASSED - the pipeline works on this device.")
except Exception:
    print("4. SCRAPE FAILED - full traceback below:")
    traceback.print_exc()
