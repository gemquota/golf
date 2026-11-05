"""Compatibility shim. Canonical entry point: python -m golf scrape"""
import sys
from golf.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["scrape", "--no-publish", *sys.argv[1:]]))
