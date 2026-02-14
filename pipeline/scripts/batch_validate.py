#!/usr/bin/env python3
"""Batch validate TypeQL queries against TypeDB using file-based approach."""

import csv
import subprocess
import sys
import json
import tempfile
import os

DB = "text2typeql_companies"
TYPEDB = "/opt/typedb-all-linux-arm64-3.8.0/typedb"
CONSOLE_ARGS = ["console", "--address", "localhost:1729", "--username", "admin", "--password", "password", "--tls-disabled"]

def validate_query(typeql: str) -> tuple[bool, str]:
    """Validate a TypeQL query against TypeDB using a temp file."""
    # Write query to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tql', delete=False) as f:
        f.write(typeql)
        temp_file = f.name

    try:
        result = subprocess.run(
            [TYPEDB] + CONSOLE_ARGS + [
                "--command", f"transaction read {DB}",
                "--command", f"source {temp_file}",
                "--command", "close"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout + result.stderr

        if result.returncode == 0 and "error:" not in output.lower():
            return True, ""
        else:
            # Extract error message
            lines = output.strip().split('\n')
            for line in lines:
                if 'error:' in line.lower():
                    # Remove ANSI codes
                    clean = line.replace('[1m', '').replace('[31m', '').replace('[0m', '').replace('[33m', '')
                    return False, clean.strip()
            return False, output[:200] if output else "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "Query timeout"
    except Exception as e:
        return False, str(e)
    finally:
        os.unlink(temp_file)

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "dataset/companies/queries.csv"

    with open(input_file, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Validating {len(rows)} queries...")

    failures = []
    for i, row in enumerate(rows):
        idx = row['original_index']
        typeql = row['typeql']

        success, error = validate_query(typeql)

        if not success:
            failures.append({
                'index': idx,
                'error': error,
                'question': row['question'],
                'cypher': row['cypher'],
                'typeql': typeql
            })
            print(f"[{i+1}/{len(rows)}] Index {idx}: FAILED - {error[:80]}")
        else:
            if (i+1) % 100 == 0:
                print(f"[{i+1}/{len(rows)}] Validated {i+1} queries, {len(failures)} failures so far")

    print(f"\n=== Summary ===")
    print(f"Total: {len(rows)}")
    print(f"Passed: {len(rows) - len(failures)}")
    print(f"Failed: {len(failures)}")

    if failures:
        print(f"\nFailed indices: {[f['index'] for f in failures]}")

        # Save failures to JSON for processing
        with open('dataset/companies/validation_failures.json', 'w') as f:
            json.dump(failures, f, indent=2)
        print(f"\nFailures saved to dataset/companies/validation_failures.json")

if __name__ == "__main__":
    main()
