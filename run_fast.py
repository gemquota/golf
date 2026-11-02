"""Deprecated compatibility shim; shared scraping logic lives in scrape_worker.py.

Use `python -m golf scrape --no-pipeline` for scrape-only operation.
"""
import sys
from golf.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["scrape", "--no-pipeline", *sys.argv[1:]]))
