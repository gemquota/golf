#!/usr/bin/env python3
"""Build raw, enriched and analysis-friendly CSV exports from the scraper DB."""
from export_csv import build_analysis_exports

if __name__ == "__main__":
    n = build_analysis_exports()
    print(f"Exported {n} DB bonuses to raw + enriched CSVs")
