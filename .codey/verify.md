# Verification record

## Original ungolf-refactor verification

The initial schema/CLI refactor was verified on 2026-11-03 with
`python3 -m unittest discover -s tests -v`: 15 tests passed. That detailed
run is retained in the original task history, but its source excerpts are
historical and must not be treated as the current repository inventory.

## Consolidated repository work

The follow-on URL-lifecycle, runtime-artifact audit, and repository cleanup
are consolidated in [PR #30](https://github.com/gemquota/golf/pull/30).

The latest audited tree before the recursive cleanup contained 123 tracked
files across 19 directories, with no truncated Git tree response. The only
byte-identical duplicate blobs were `viewer/icon.svg` and
`viewer/public/icon.svg`; both are intentionally retained for distinct
package and Vite public-asset roles.

The PR's latest recorded CI validation covers:
- Python unit tests and compile checks.
- Maintenance pipeline and standard-library cleaner regression tests.
- Daily bonus-history tests and the viewer production build.

Do not use the original AC-3/AC-4 excerpts below as current state: the
compatibility wrappers and `build_exports.py` mentioned there have since
been retired. The canonical CLI is `python -m golf`, and exports are owned
by `export_csv.py` and `export_viewer_data.py`.
