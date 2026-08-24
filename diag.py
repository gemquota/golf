#!/usr/bin/env python3
"""Diagnose why sites are failing on this device.

Compares plain requests vs cloudscraper against one URL with full tracebacks.
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

# --- Test A: plain requests ---
print("A) plain requests:")
try:
    import requests
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    cf = "cf-mitigated" in resp.headers or resp.status_code == 403
    print(f"   HTTP {resp.status_code}, {len(resp.text)} bytes{' (Cloudflare block?)' if cf else ''}")
    plain_ok = resp.status_code == 200
except Exception as e:
    print(f"   FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    plain_ok = False

# --- Test B: cloudscraper ---
print("B) cloudscraper:")
try:
    import cloudscraper
    print(f"   version {cloudscraper.__version__}")
except Exception as e:
    print(f"   IMPORT FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    session = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    session.headers.update(HEADERS)
    resp = session.get(URL, timeout=20)
    print(f"   HTTP {resp.status_code}, {len(resp.text)} bytes")
    markers = "MERCHANTID" in resp.text
    print(f"   MERCHANTID marker found: {markers}")
    scraper_ok = resp.status_code == 200 and markers
except Exception as e:
    print(f"   FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    scraper_ok = False

# --- Verdict ---
print()
if scraper_ok:
    print("VERDICT: cloudscraper works - failure is elsewhere (login/API/config).")
    print("Run: python3 diag_full.py  (or share dashboard error codes)")
elif plain_ok:
    print("VERDICT: plain requests works but cloudscraper does not.")
    print("-> Fix: set engine=requests in in/config/config.ini [SETTINGS]")
else:
    print("VERDICT: BOTH transports fail -> network-level problem on this device")
    print("(DNS, carrier blocking, or TLS). Try another connection (wifi vs data).")
