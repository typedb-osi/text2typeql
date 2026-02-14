#!/usr/bin/env python3
"""Standardize camelCase variable names and fetch keys to snake_case in TypeQL queries.

Two transformations per query:
  1. Variables: $movieCount -> $movie_count
  2. Fetch keys: "numReviews": -> "num_reviews":

Usage:
  fix_camelcase_vars.py --dry-run                    # Preview changes
  fix_camelcase_vars.py --apply                      # Fix query CSVs
  fix_camelcase_vars.py --apply --include-analysis   # Also fix analysis CSVs
"""

import csv
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
ANALYSIS_DIR = REPO_ROOT / "docs" / "neo_semantic_analysis"

# Match camelCase: starts lowercase, has at least one uppercase letter
CAMEL_RE = re.compile(r'[a-z]+[A-Z]')

# Match $variable names in TypeQL
VAR_RE = re.compile(r'\$([a-zA-Z_]\w*)')

# Match "key": patterns in fetch blocks (key followed by colon = fetch key, not string value)
FETCH_KEY_RE = re.compile(r'"([a-zA-Z_]\w*)"\s*:')


def camel_to_snake(name: str) -> str:
    """Convert camelCase or mixedCase to snake_case.

    Handles acronyms: orderID -> order_id, boardMemberCEOCount -> board_member_ceo_count
    """
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    return s.lower()


def is_camel_case(name: str) -> bool:
    """Check if a name contains camelCase (lowercase followed by uppercase)."""
    return bool(CAMEL_RE.search(name))


def fix_typeql(typeql: str) -> str:
    """Transform camelCase variables and fetch keys to snake_case."""
    result = typeql

    # 1. Fix variables: find all $camelCase, replace longest-first
    var_names = set()
    for m in VAR_RE.finditer(result):
        name = m.group(1)
        if is_camel_case(name):
            var_names.add(name)

    # Sort longest first to avoid substring replacement issues
    for name in sorted(var_names, key=len, reverse=True):
        snake = camel_to_snake(name)
        # Use word boundary after variable name to avoid partial matches
        result = re.sub(r'\$' + re.escape(name) + r'(?!\w)', '$' + snake, result)

    # 2. Fix fetch keys: "camelCase": -> "snake_case":
    def replace_key(m):
        key = m.group(1)
        if is_camel_case(key):
            return '"' + camel_to_snake(key) + '"' + m.group(0)[len(m.group(1)) + 2:]
        return m.group(0)

    result = FETCH_KEY_RE.sub(replace_key, result)

    return result


def process_csv(csv_path: Path, dry_run: bool, typeql_col: str = 'typeql') -> int:
    """Process a CSV file. Returns number of fixed rows."""
    if not csv_path.exists():
        return 0

    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if typeql_col not in fieldnames:
        return 0

    fixed_count = 0
    for row in rows:
        original = row[typeql_col]
        fixed = fix_typeql(original)
        if fixed != original:
            fixed_count += 1
            if dry_run:
                idx = row.get('original_index', '?')
                db = csv_path.parent.name
                # Show first variable and first key change
                orig_vars = set(VAR_RE.findall(original))
                fixed_vars = set(VAR_RE.findall(fixed))
                changed = orig_vars - fixed_vars
                if changed:
                    sample = sorted(changed)[0]
                    print(f"  [{db}] index {idx}: ${sample} -> ${camel_to_snake(sample)}")
            else:
                row[typeql_col] = fixed

    if not dry_run and fixed_count > 0:
        # Atomic write: tempfile + rename
        fd, tmp_path = tempfile.mkstemp(dir=csv_path.parent, suffix='.csv')
        try:
            with os.fdopen(fd, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(tmp_path, csv_path)
        except:
            os.unlink(tmp_path)
            raise

        # Verify row count preserved
        with open(csv_path, 'r', newline='') as f:
            verify = len(list(csv.DictReader(f)))
        assert verify == len(rows), f"Row count mismatch: {verify} != {len(rows)}"

    return fixed_count


def main():
    dry_run = '--dry-run' in sys.argv
    apply = '--apply' in sys.argv
    include_analysis = '--include-analysis' in sys.argv

    if not dry_run and not apply:
        print("Usage: fix_camelcase_vars.py --dry-run | --apply [--include-analysis]")
        sys.exit(1)

    mode = "DRY RUN" if dry_run else "APPLYING"
    print(f"=== {mode}: Standardize camelCase to snake_case ===\n")

    # Process all 22 databases
    total_fixed = 0
    for source in ["synthetic-1", "synthetic-2"]:
        source_dir = DATASET_DIR / source
        if not source_dir.exists():
            continue
        for db_dir in sorted(source_dir.iterdir()):
            if not db_dir.is_dir():
                continue
            csv_path = db_dir / "queries.csv"
            count = process_csv(csv_path, dry_run)
            if count > 0:
                print(f"  {source}/{db_dir.name}: {count} queries {'would be ' if dry_run else ''}fixed")
            total_fixed += count

    print(f"\nQuery CSVs: {total_fixed} total fixes")

    # Analysis CSVs
    if include_analysis or dry_run:
        analysis_fixed = 0
        for csv_path in sorted(ANALYSIS_DIR.glob("*.csv")):
            count = process_csv(csv_path, dry_run)
            if count > 0:
                print(f"  {csv_path.name}: {count} rows {'would be ' if dry_run else ''}fixed")
                analysis_fixed += count
        print(f"Analysis CSVs: {analysis_fixed} total fixes")

    if not dry_run:
        print("\nDone. Run with --dry-run to verify 0 remaining.")


if __name__ == "__main__":
    main()
