#!/usr/bin/env python3
"""Validate all companies queries against TypeDB and perform semantic review."""

import csv
import subprocess
import sys
import re
import json
from pathlib import Path

# Results tracking
validation_failures = []
semantic_issues = []
passed_queries = []

def validate_typeql(typeql: str, index: int) -> tuple[bool, str]:
    """Validate TypeQL against TypeDB server."""
    # Write query to temp file
    with open('/tmp/test.tql', 'w') as f:
        f.write(typeql)

    # Run TypeDB console
    cmd = [
        '/opt/typedb-all-linux-arm64-3.8.0/typedb', 'console',
        '--address', 'localhost:1729',
        '--username', 'admin',
        '--password', 'password',
        '--tls-disabled',
        '--command', 'transaction read text2typeql_companies',
        '--command', 'source /tmp/test.tql',
        '--command', 'close'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr

        # Check for errors
        if 'Error' in output or 'error' in output.lower():
            # Extract error message
            error_lines = [l for l in output.split('\n') if 'error' in l.lower() or 'Error' in l]
            return False, '\n'.join(error_lines[:3])

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def semantic_review(index: int, question: str, cypher: str, typeql: str) -> tuple[bool, str]:
    """Perform semantic review to check if TypeQL matches the question intent."""
    issues = []
    question_lower = question.lower()
    typeql_lower = typeql.lower()

    # Check 1: Entity type matching
    # If question asks for "organizations", query should fetch organization data
    if 'organization' in question_lower and 'isa organization' not in typeql_lower:
        if 'isa person' in typeql_lower and 'isa organization' not in typeql_lower:
            issues.append("Question asks about organizations but query only matches persons")

    if 'person' in question_lower or 'ceo' in question_lower or 'board member' in question_lower:
        if 'isa person' not in typeql_lower and '$p' not in typeql_lower:
            if 'ceo' in question_lower and 'ceo_of' not in typeql_lower:
                issues.append("Question asks about CEOs but no person/ceo_of in query")

    # Check 2: Relation directions
    # investor/invested patterns
    if 'investor' in question_lower:
        if 'invested_in' in typeql_lower:
            # Check role assignment
            if 'invest' in question_lower and 'organization' in question_lower:
                pass  # Complex, needs manual review

    # subsidiary patterns
    if 'subsidiary' in question_lower or 'subsidiaries' in question_lower:
        if 'subsidiary_of' not in typeql_lower:
            issues.append("Question mentions subsidiaries but no subsidiary_of relation")

    if 'parent' in question_lower and 'organization' in question_lower:
        if 'subsidiary_of' in typeql_lower:
            # Check parent/subsidiary roles
            pass

    # Check 3: Location patterns
    if 'in country' in question_lower or 'country' in question_lower:
        if 'country' in question_lower and 'isa country' not in typeql_lower:
            if 'location-contains' not in typeql_lower and 'country_name' not in typeql_lower:
                # May need location-contains for city->country
                pass

    # Check 4: OPTIONAL MATCH handling
    if 'OPTIONAL MATCH' in cypher:
        if 'try {' not in typeql_lower and 'or {' not in typeql_lower:
            issues.append("Cypher has OPTIONAL MATCH but TypeQL lacks try/or blocks")

    # Check 5: HAVING / aggregation filtering
    if 'HAVING' in cypher.upper() or (re.search(r'WITH\s+\w+.*count.*WHERE', cypher, re.I|re.DOTALL)):
        # Check for chained reduce pattern
        if 'reduce' in typeql_lower:
            # Look for match after reduce
            reduce_pos = typeql_lower.find('reduce')
            after_reduce = typeql_lower[reduce_pos:]
            if 'match' not in after_reduce.split('reduce')[1] if 'reduce' in after_reduce else True:
                pass  # May need chained reduce

    # Check 6: COUNT/aggregation correctness
    if 'count' in question_lower or 'how many' in question_lower or 'number of' in question_lower:
        if 'reduce' not in typeql_lower and 'count' not in typeql_lower:
            issues.append("Question asks for count but no reduce/count in query")

    # Check 7: Top N / ordering
    if 'top' in question_lower or 'highest' in question_lower or 'most' in question_lower:
        if 'desc' not in typeql_lower:
            # Check if sort is present
            if 'sort' not in typeql_lower and 'limit' in typeql_lower:
                issues.append("Question asks for top/highest but no descending sort")

    if 'lowest' in question_lower or 'least' in question_lower or 'fewest' in question_lower:
        if 'asc' not in typeql_lower and 'sort' in typeql_lower:
            pass  # asc is default
        elif 'desc' in typeql_lower:
            issues.append("Question asks for lowest but query sorts descending")

    # Check 8: Both/and conditions
    if ' and ' in question_lower and 'both' in question_lower:
        # Complex condition, flag for review
        pass

    # Check 9: Negation patterns
    if 'not ' in question_lower or "don't" in question_lower or "doesn't" in question_lower:
        if 'not {' not in typeql_lower and 'not{' not in typeql_lower:
            issues.append("Question has negation but TypeQL lacks 'not { }' block")

    # Check 10: Distinct handling
    if 'DISTINCT' in cypher and 'distinct' not in typeql_lower:
        # TypeQL fetch usually returns distinct by default, but aggregations may need care
        pass

    # Check 11: Competitors relation (symmetric)
    if 'competitor' in question_lower:
        if 'competes_with' not in typeql_lower:
            issues.append("Question about competitors but no competes_with relation")

    # Check 12: Suppliers/customers
    if 'supplier' in question_lower or 'supply' in question_lower:
        if 'supplies' not in typeql_lower:
            issues.append("Question about suppliers but no supplies relation")

    if 'customer' in question_lower:
        if 'supplies' not in typeql_lower:
            issues.append("Question about customers but no supplies relation")

    if issues:
        return False, "; ".join(issues)
    return True, ""


def main():
    """Main validation loop."""
    # Read queries
    with open('/opt/text2typeql/dataset/companies/queries.csv', 'r') as f:
        reader = csv.DictReader(f)
        queries = list(reader)

    print(f"Total queries to review: {len(queries)}")
    print("=" * 60)

    # Process queries
    for i, row in enumerate(queries):
        index = int(row['original_index'])
        question = row['question']
        cypher = row['cypher']
        typeql = row['typeql']

        # Progress indicator
        if (i + 1) % 50 == 0:
            print(f"Progress: {i + 1}/{len(queries)} queries processed")

        # Step 1: Validate against TypeDB
        valid, error = validate_typeql(typeql, index)

        if not valid:
            validation_failures.append({
                'index': index,
                'question': question[:100],
                'error': error
            })
            continue

        # Step 2: Semantic review
        sem_valid, sem_issue = semantic_review(index, question, cypher, typeql)

        if not sem_valid:
            semantic_issues.append({
                'index': index,
                'question': question[:100],
                'issue': sem_issue
            })
        else:
            passed_queries.append(index)

    # Print results
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    print(f"\nTotal queries reviewed: {len(queries)}")
    print(f"Passed both validation and semantic review: {len(passed_queries)}")
    print(f"Validation failures: {len(validation_failures)}")
    print(f"Semantic issues: {len(semantic_issues)}")

    if validation_failures:
        print("\n--- VALIDATION FAILURES ---")
        for vf in validation_failures[:20]:  # Show first 20
            print(f"Index {vf['index']}: {vf['error'][:100]}")
        if len(validation_failures) > 20:
            print(f"... and {len(validation_failures) - 20} more")

    if semantic_issues:
        print("\n--- SEMANTIC ISSUES ---")
        for si in semantic_issues[:30]:  # Show first 30
            print(f"Index {si['index']}: {si['issue']}")
        if len(semantic_issues) > 30:
            print(f"... and {len(semantic_issues) - 30} more")

    # Save results to file
    with open('/tmp/companies_review_results.json', 'w') as f:
        json.dump({
            'total': len(queries),
            'passed': len(passed_queries),
            'validation_failures': validation_failures,
            'semantic_issues': semantic_issues,
            'passed_indices': passed_queries
        }, f, indent=2)

    print(f"\nDetailed results saved to /tmp/companies_review_results.json")

if __name__ == '__main__':
    main()
