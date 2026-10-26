"""Compatibility shim. The canonical entry point is golf.py."""
import sys
from golf import main

if __name__ == "__main__":
    raise SystemExit(main(["interactive", *sys.argv[1:]]))
