#!/usr/bin/env python3
"""Fix deprecated relation syntax: (roles) isa type -> type (roles).

Two cases:
  Case 1: (role: $a, role: $b) isa type;        -> type (role: $a, role: $b);
  Case 2: (role: $a, role: $b) isa type, has ... -> $_ isa type (role: $a, role: $b), has ...

Usage:
  fix_relation_syntax.py --dry-run                    # Preview changes
  fix_relation_syntax.py --apply                      # Fix query CSVs
  fix_relation_syntax.py --apply --include-analysis   # Also fix analysis CSVs
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

# Pattern 1: type (roles) isa type — redundant form (type stated twice)
# Must come before Pattern 2 since it's more specific
PATTERN_REDUNDANT = re.compile(
    r'(?P<leading>[\w-]+)'   # leading type name
    r'\s+'
    r'\((?P<roles>[^)]*:\s*\$[\w_]+[^)]*)\)'  # (role: $var, ...)
    r'\s+isa\s+'
    r'(?P=leading)'          # same type name repeated (backreference)
)

# Pattern 2: (role: $var, ...) isa type_name — the common deprecated form
PATTERN = re.compile(
    r'(?<!\$\w)'           # not preceded by $var (variable char)
    r'(?<!\w)'             # not preceded by word char (avoids partial match)
    r'\((?P<roles>[^)]*:\s*\$[\w_]+[^)]*)\)'  # (role: $var, ...)
    r'\s+isa\s+'           # isa keyword
    r'(?P<type>[\w-]+)'    # type name (supports hyphens)
)


def fix_typeql(typeql: str) -> str:
    """Transform deprecated relation syntax to modern form."""

    # First: fix redundant form `type (roles) isa type` -> `type (roles)` or `$_ isa type (roles)`
    def replace_redundant(m):
        rel_type = m.group('leading')
        roles = m.group('roles')
        after = typeql[m.end():]
        if after.lstrip().startswith(', has') or after.lstrip().startswith(',has'):
            return f'$_ isa {rel_type} ({roles})'
        return f'{rel_type} ({roles})'

    result = PATTERN_REDUNDANT.sub(replace_redundant, typeql)

    # Then: fix common form `(roles) isa type` -> `type (roles)` or `$_ isa type (roles)`
    def replace_match(m):
        roles = m.group('roles')
        rel_type = m.group('type')
        after = result[m.end():]
        if after.lstrip().startswith(', has') or after.lstrip().startswith(',has'):
            return f'$_ isa {rel_type} ({roles})'
        return f'{rel_type} ({roles})'

    return PATTERN.sub(replace_match, result)


def process_query_csv(csv_path: Path, dry_run: bool) -> int:
    """Process a queries.csv file. Returns number of fixed queries."""
    if not csv_path.exists():
        return 0

    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixed_count = 0
    for row in rows:
        original = row['typeql']
        fixed = fix_typeql(original)
        if fixed != original:
            fixed_count += 1
            if dry_run:
                idx = row.get('original_index', '?')
                print(f"  [{csv_path.parent.name}] index {idx}:")
                # Show first change
                for orig_line, fix_line in zip(original.split('\n'), fixed.split('\n')):
                    if orig_line != fix_line:
                        print(f"    - {orig_line.strip()}")
                        print(f"    + {fix_line.strip()}")
                        break
            else:
                row['typeql'] = fixed

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


def process_analysis_csv(csv_path: Path, dry_run: bool) -> int:
    """Process an analysis CSV file. Returns number of fixed rows."""
    if not csv_path.exists():
        return 0

    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if 'typeql' not in fieldnames:
        return 0

    fixed_count = 0
    for row in rows:
        original = row['typeql']
        fixed = fix_typeql(original)
        if fixed != original:
            fixed_count += 1
            if not dry_run:
                row['typeql'] = fixed

    if not dry_run and fixed_count > 0:
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

    return fixed_count


def main():
    dry_run = '--dry-run' in sys.argv
    apply = '--apply' in sys.argv
    include_analysis = '--include-analysis' in sys.argv

    if not dry_run and not apply:
        print("Usage: fix_relation_syntax.py --dry-run | --apply [--include-analysis]")
        sys.exit(1)

    mode = "DRY RUN" if dry_run else "APPLYING"
    print(f"=== {mode}: Fix deprecated relation syntax ===\n")

    # Affected database CSV files
    affected = [
        ("synthetic-1", "companies"),
        ("synthetic-1", "movies"),
        ("synthetic-1", "gameofthrones"),
        ("synthetic-1", "recommendations"),
        ("synthetic-1", "neoflix"),
        ("synthetic-1", "twitch"),
        ("synthetic-2", "companies"),
        ("synthetic-2", "movies"),
    ]

    total_fixed = 0
    for source, db in affected:
        csv_path = DATASET_DIR / source / db / "queries.csv"
        count = process_query_csv(csv_path, dry_run)
        if count > 0:
            print(f"  {source}/{db}: {count} queries {'would be ' if dry_run else ''}fixed")
        total_fixed += count

    print(f"\nQuery CSVs: {total_fixed} total fixes")

    # Analysis CSVs
    if include_analysis or dry_run:
        analysis_fixed = 0
        for csv_path in sorted(ANALYSIS_DIR.glob("*.csv")):
            count = process_analysis_csv(csv_path, dry_run)
            if count > 0:
                print(f"  {csv_path.name}: {count} rows {'would be ' if dry_run else ''}fixed")
                analysis_fixed += count
        print(f"Analysis CSVs: {analysis_fixed} total fixes")

    if not dry_run:
        print("\nDone. Run with --dry-run to verify 0 remaining.")


if __name__ == "__main__":
    main()
