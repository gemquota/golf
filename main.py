"""Compatibility shim. Canonical entry point: python -m golf interactive"""
import sys
from golf.cli import main

if __name__ == "__main__":
    # Preserve legacy flags (-r/-s/-v) by forwarding after the subcommand.
    raise SystemExit(main(["interactive", *sys.argv[1:]]))
