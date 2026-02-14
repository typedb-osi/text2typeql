#!/usr/bin/env python3
"""Validate a single TypeQL query against TypeDB.

Usage:
    python3 scripts/validate_typeql.py <database> '<typeql_query>'
    python3 scripts/validate_typeql.py <database> --file /path/to/query.tql
    echo '<typeql>' | python3 scripts/validate_typeql.py <database> --stdin

Returns:
    Exit code 0 on success, 1 on failure
    Prints "OK" on success, or error message on failure

Examples:
    python3 scripts/validate_typeql.py companies 'match $o isa organization; limit 3; fetch { "name": $o.name };'
    python3 scripts/validate_typeql.py twitter --file /tmp/query.tql
"""

import subprocess
import sys
import tempfile
import os

TYPEDB = "/opt/typedb-all-linux-arm64-3.8.0/typedb"
CONSOLE_ARGS = ["console", "--address", "localhost:1729", "--username", "admin", "--password", "password", "--tls-disabled"]


def validate_query(database: str, typeql: str) -> tuple[bool, str]:
    """Validate a TypeQL query against TypeDB.

    Args:
        database: Database name (without text2typeql_ prefix)
        typeql: The TypeQL query to validate

    Returns:
        (success, message) tuple
    """
    db_name = f"text2typeql_{database}" if not database.startswith("text2typeql_") else database

    # Write query to temp file (avoids shell escaping issues)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tql', delete=False) as f:
        f.write(typeql)
        temp_file = f.name

    try:
        result = subprocess.run(
            [TYPEDB] + CONSOLE_ARGS + [
                "--command", f"transaction read {db_name}",
                "--command", f"source {temp_file}",
                "--command", "close"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout + result.stderr

        # Clean ANSI codes
        for code in ['[1m', '[31m', '[0m', '[33m', '[32m', '[34m']:
            output = output.replace(code, '')

        if result.returncode == 0 and "error:" not in output.lower():
            return True, "OK"
        else:
            # Extract error message - look for specific error codes like [INF2], [QUA1], etc.
            lines = output.strip().split('\n')
            error_lines = []
            for line in lines:
                # Capture lines with TypeDB error codes or "error:" prefix
                if any(code in line for code in ['[INF', '[QUA', '[QEX', '[REP', '[TYP', '[SYN']) or \
                   ('error:' in line.lower() and 'Error executing' not in line):
                    error_lines.append(line.strip())
            if error_lines:
                return False, '; '.join(error_lines[:3])  # Return up to 3 error lines
            # Fallback to old behavior
            for line in lines:
                if 'error:' in line.lower():
                    return False, line.strip()
            # Return last non-empty line if no explicit error
            for line in reversed(lines):
                if line.strip():
                    return False, line.strip()
            return False, "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "Query timeout (30s)"
    except FileNotFoundError:
        return False, f"TypeDB not found at {TYPEDB}. Is TypeDB installed?"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            os.unlink(temp_file)
        except:
            pass


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    database = sys.argv[1]

    # Get query from various sources
    if len(sys.argv) >= 3:
        if sys.argv[2] == '--stdin':
            typeql = sys.stdin.read()
        elif sys.argv[2] == '--file':
            if len(sys.argv) < 4:
                print("Error: --file requires a path argument", file=sys.stderr)
                sys.exit(1)
            with open(sys.argv[3], 'r') as f:
                typeql = f.read()
        else:
            # Query passed as argument
            typeql = sys.argv[2]
    else:
        print("Error: No query provided. Use --file <path> or --stdin flag, or pass query as argument.", file=sys.stderr)
        sys.exit(1)

    success, message = validate_query(database, typeql)
    print(message)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
