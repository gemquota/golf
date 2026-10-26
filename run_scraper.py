"""Compatibility shim for the canonical full scrape pipeline.

Use `python golf.py scrape` for new automation.
"""
import sys
from golf import main

if __name__ == "__main__":
    raise SystemExit(main(["scrape", *sys.argv[1:]]))
