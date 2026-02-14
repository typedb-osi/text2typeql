#!/usr/bin/env python3
"""Remove a row from a CSV file by original_index."""

import csv
import sys
import tempfile
import os

def remove_row(csv_path: str, index: int) -> bool:
    """Remove row with given original_index from CSV. Returns True if found and removed."""
    rows = []
    found = False
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if str(row.get('original_index', '')) == str(index):
                found = True
                continue
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
    if len(sys.argv) != 3:
        print("Usage: csv_remove_row.py <csv_path> <original_index>", file=sys.stderr)
        sys.exit(1)
    found = remove_row(sys.argv[1], int(sys.argv[2]))
    print("removed" if found else "not_found")
    sys.exit(0 if found else 1)
