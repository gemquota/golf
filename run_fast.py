"""Deprecated compatibility shim; shared scraping logic lives in scraper.py.

Use `python golf.py scrape --no-pipeline` for scrape-only operation.
"""
import sys
from golf import main

if __name__ == "__main__":
    raise SystemExit(main(["scrape", "--no-pipeline", *sys.argv[1:]]))
