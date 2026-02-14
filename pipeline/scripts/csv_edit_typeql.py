#!/usr/bin/env python3
"""Edit the typeql field of a row in queries.csv by original_index."""

import csv
import sys
import tempfile
import os

def edit_typeql(csv_path: str, index: int, new_typeql: str) -> bool:
    """Replace the typeql field for the row with given original_index. Returns True if found."""
    rows = []
    found = False
    fieldnames = None

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if str(row.get('original_index', '')) == str(index):
                row['typeql'] = new_typeql
                found = True
            rows.append(row)

    if found:
        with tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(csv_path),
                                          delete=False, suffix='.csv', newline='') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            tmp_path = tmp.name
        os.replace(tmp_path, csv_path)

    return found

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: csv_edit_typeql.py <csv_path> <original_index> <new_typeql>", file=sys.stderr)
        sys.exit(1)
    found = edit_typeql(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    print("updated" if found else "not_found")
    sys.exit(0 if found else 1)
