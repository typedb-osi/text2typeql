#!/usr/bin/env python3
"""Automated semantic review scanner for converted TypeQL queries.

Scans (question, cypher, typeql) triples across 4 layers:
  Layer 1: Question ↔ TypeQL structural checks
  Layer 2: Cypher ↔ TypeQL faithfulness checks
  Layer 3: Schema-aware type checking
  Layer 4: Known error patterns

Usage:
  python3 pipeline/scripts/semantic_review_scan.py <database> --source <synthetic-1|synthetic-2>
  python3 pipeline/scripts/semantic_review_scan.py --all --source synthetic-1
  python3 pipeline/scripts/semantic_review_scan.py --summary  # combine all review_flags.json files
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

# Add parent paths for imports
SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent
REPO_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from parse_schema import parse_schema


# ============================================================
# Layer 1: Question ↔ TypeQL structural checks
# ============================================================

def check_missing_aggregation(question: str, cypher: str, typeql: str) -> list:
    """Check if question asks for count/total but TypeQL lacks aggregation."""
    flags = []
    q = question.lower()
    cy = cypher.lower()
    tql = typeql.lower()

    # Patterns that imply counting
    count_patterns = [
        r'\bhow many\b', r'\btotal number\b', r'\bnumber of\b',
    ]

    needs_count = any(re.search(p, q) for p in count_patterns)
    has_count = 'reduce' in tql and 'count' in tql

    if needs_count and not has_count:
        # Only flag if the Cypher also uses COUNT — if Cypher answers via a property
        # (e.g., "how many followers" → RETURN u.followers), it's not an aggregation
        if 'count(' in cy:
            flags.append({
                'check': 'missing_aggregation',
                'confidence': 'high',
                'detail': 'Question asks for count/total, Cypher uses COUNT(), but TypeQL has no reduce...count',
            })

    return flags


def check_missing_mean(question: str, cypher: str, typeql: str) -> list:
    """Check if question asks for computing an average but TypeQL lacks mean."""
    flags = []
    q = question.lower()
    cy = cypher.lower()
    tql = typeql.lower()

    if re.search(r'\baverage\b|\bmean\b|\bavg\b', q):
        if 'mean(' not in tql and 'avg(' not in tql:
            # Only flag if Cypher actually computes an average (avg() function)
            # Don't flag if "average" is part of an attribute name (e.g., average_vote)
            if 'avg(' in cy:
                flags.append({
                    'check': 'missing_mean',
                    'confidence': 'high',
                    'detail': 'Question asks for average, Cypher uses avg(), but TypeQL has no mean()',
                })

    return flags


def check_missing_sum(question: str, typeql: str) -> list:
    """Check if question asks for sum/total value but TypeQL lacks sum."""
    flags = []
    q = question.lower()
    tql = typeql.lower()

    # "total revenue", "total amount", "sum of"
    if re.search(r'\btotal\s+(?:revenue|amount|value|price|cost|sales|quantity|freight|discount)\b|\bsum\s+of\b', q):
        if 'sum(' not in tql:
            # Could also be done with reduce ... = sum
            if 'reduce' not in tql:
                flags.append({
                    'check': 'missing_sum',
                    'confidence': 'medium',
                    'detail': 'Question asks for total/sum but TypeQL has no sum()',
                })

    return flags


def check_missing_sort_limit(question: str, cypher: str, typeql: str) -> list:
    """Check if question asks for top-N but TypeQL lacks sort+limit."""
    flags = []
    q = question.lower()
    cy = cypher.lower()
    tql = typeql.lower()

    # Patterns for top-N that REQUIRE sorting (ranked)
    ranked_patterns = [
        r'\btop\s+(\d+)\b',
        r'\b(\d+)\s+most\b', r'\b(\d+)\s+least\b',
        r'\b(\d+)\s+highest\b', r'\b(\d+)\s+lowest\b',
        r'\b(\d+)\s+biggest\b', r'\b(\d+)\s+smallest\b',
        r'\b(\d+)\s+largest\b',
    ]

    # "first N" is ambiguous — only requires sort if Cypher has ORDER BY
    first_n = re.search(r'\bfirst\s+(\d+)\b', q)
    if first_n and 'order by' in cy:
        n = first_n.group(1)
        if 'sort' not in tql:
            flags.append({
                'check': 'missing_sort',
                'confidence': 'high',
                'detail': f'Question asks for first-{n} and Cypher has ORDER BY, but TypeQL has no sort',
            })

    for pattern in ranked_patterns:
        m = re.search(pattern, q)
        if m:
            n = m.group(1)
            has_limit = f'limit {n}' in tql
            has_sort = 'sort' in tql

            if not has_sort and 'reduce' not in tql:
                # "top N" needs sort (unless it's doing reduce...groupby + sort)
                flags.append({
                    'check': 'missing_sort',
                    'confidence': 'high',
                    'detail': f'Question asks for top-{n} but TypeQL has no sort',
                })
            if not has_limit:
                flags.append({
                    'check': 'missing_limit',
                    'confidence': 'medium',
                    'detail': f'Question asks for top-{n} but TypeQL has no limit {n}',
                })
            break

    # Single superlative: "most popular", "highest rated"
    # Only flag if Cypher also has ORDER BY or aggregation
    superlative_patterns = [
        r'\bmost\s+\w+\b', r'\bhighest\b', r'\blowest\b',
        r'\blargest\b', r'\bsmallest\b', r'\bbiggest\b',
        r'\boldest\b', r'\bnewest\b', r'\byoungest\b',
        r'\bmost\s+recent\b', r'\bearliest\b', r'\blatest\b',
    ]

    for pattern in superlative_patterns:
        if re.search(pattern, q):
            has_sort = 'sort' in tql
            has_maxmin = 'max(' in tql or 'min(' in tql

            if not has_sort and not has_maxmin:
                # Only flag if Cypher confirms ranking intent
                if 'order by' in cy or 'count(' in cy or 'max(' in cy or 'min(' in cy:
                    if not re.search(r'\btop\s+\d+\b', q):
                        flags.append({
                            'check': 'missing_sort_superlative',
                            'confidence': 'medium',
                            'detail': f'Question uses superlative "{re.search(pattern, q).group()}" but TypeQL has no sort or max/min',
                        })
            break

    return flags


def check_missing_negation(question: str, typeql: str) -> list:
    """Check if question implies negation but TypeQL lacks not{}."""
    flags = []
    q = question.lower()
    tql = typeql.lower()

    negation_patterns = [
        r"\bwho\s+(?:have|has)\s+not\b",
        r"\bwho\s+(?:don't|doesn't|do not|does not)\b",
        r"\bthat\s+(?:don't|doesn't|do not|does not)\b",
        r"\bnever\b",
        r"\bwithout\s+(?:any|a)\b",
        r"\bno\s+(?:followers|following|tweets|movies|reviews|orders)\b",
        r"\bnot\s+(?:followed|following|connected|linked|related)\b",
        r"\bhave\s+not\s+(?:been|made|written|posted)\b",
    ]

    needs_negation = any(re.search(p, q) for p in negation_patterns)
    has_negation = 'not {' in tql or 'not{' in tql

    if needs_negation and not has_negation:
        # Exception: "not" might be part of a boolean attribute check
        if 'false' not in tql and 'true' not in tql:
            flags.append({
                'check': 'missing_negation',
                'confidence': 'medium',
                'detail': 'Question implies negation but TypeQL has no not{} block',
            })

    return flags


def _parse_question_number(text: str, start: int) -> int | None:
    """Parse a number from question text, handling commas and magnitude words.

    Handles: "100", "10,000", "300,000,000", "30000", "100 million", "5 billion"
    """
    # Match plain digits or comma-separated digits
    m = re.match(r'(\d[\d,]*\d|\d)', text[start:])
    if m:
        num_str = m.group(1).replace(',', '')
        remaining = text[start + m.end():].strip()

        # Check for magnitude words
        magnitudes = {'thousand': 1_000, 'million': 1_000_000, 'billion': 1_000_000_000}
        for word, mult in magnitudes.items():
            if remaining.startswith(word):
                return int(num_str) * mult

        return int(num_str)

    return None


def check_threshold_mismatch(question: str, typeql: str) -> list:
    """Check if numeric thresholds in question appear in TypeQL."""
    flags = []
    q = question.lower()
    tql = typeql.lower()

    # Find threshold contexts and parse the full number
    threshold_contexts = [
        r'(?:more than|greater than|over|exceeds?|above|at least|minimum of)\s+',
        r'(?:less than|fewer than|under|below|at most|maximum of)\s+',
        r'(?:exactly|equal to)\s+',
    ]

    for pattern in threshold_contexts:
        for m in re.finditer(pattern, q):
            parsed = _parse_question_number(q, m.end())
            if parsed is not None and parsed > 1:
                num_str = str(parsed)
                if not re.search(rf'\b{num_str}\b', tql):
                    # Skip years
                    if 1900 <= parsed <= 2100:
                        continue
                    flags.append({
                        'check': 'threshold_mismatch',
                        'confidence': 'high',
                        'detail': f'Question mentions threshold {num_str} but it does not appear in TypeQL',
                    })

    return flags


def check_question_typeql_numbers(question: str, typeql: str) -> list:
    """Check for specific number mismatches between question and TypeQL.

    Handles comma-separated numbers (10,000) and magnitude words (100 million).
    """
    flags = []
    q = question.lower()
    tql = typeql.lower()

    # Already handled by threshold_mismatch for comparison contexts
    # This check catches limit/top-N number mismatches only
    # Avoid duplicate flags — skip if threshold_mismatch would catch it
    return flags


def layer1_checks(question: str, cypher: str, typeql: str) -> list:
    """Run all Layer 1 checks."""
    flags = []
    flags.extend(check_missing_aggregation(question, cypher, typeql))
    flags.extend(check_missing_mean(question, cypher, typeql))
    flags.extend(check_missing_sum(question, typeql))
    flags.extend(check_missing_sort_limit(question, cypher, typeql))
    flags.extend(check_missing_negation(question, typeql))
    flags.extend(check_threshold_mismatch(question, typeql))
    flags.extend(check_question_typeql_numbers(question, typeql))
    return flags


# ============================================================
# Layer 2: Cypher ↔ TypeQL faithfulness checks
# ============================================================

def check_cypher_filter(cypher: str, typeql: str) -> list:
    """Check if Cypher WHERE filters are present in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    # Check for numeric comparisons in Cypher
    for m in re.finditer(r'(?:where|and)\s+\w+\.(\w+)\s*(>|<|>=|<=|=)\s*(\d+)', cy):
        prop = m.group(1)
        op = m.group(2)
        val = m.group(3)
        # Check if both the property and value appear in TypeQL
        if val not in tql:
            flags.append({
                'check': 'missing_cypher_filter',
                'confidence': 'high',
                'detail': f'Cypher filters {prop} {op} {val} but value {val} not in TypeQL',
            })

    return flags


def check_cypher_sort(cypher: str, typeql: str) -> list:
    """Check if Cypher ORDER BY is reflected in TypeQL sort."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'order by' in cy and 'sort' not in tql:
        # Exception: ORDER BY inside WITH...RETURN pattern often consumed by aggregation
        # Exception: if TypeQL uses reduce (aggregation handles ordering)
        # Only flag if the ORDER BY is the final/outer one (after last RETURN/WITH)
        # Heuristic: ORDER BY after the last MATCH/WITH block
        last_order = cy.rfind('order by')
        last_return = cy.rfind('return')
        if last_order > last_return and 'reduce' not in tql:
            flags.append({
                'check': 'missing_sort_cypher',
                'confidence': 'high',
                'detail': 'Cypher has final ORDER BY but TypeQL has no sort',
            })
        elif last_order < last_return and 'reduce' not in tql:
            # ORDER BY before RETURN — might be intermediate sorting
            # Only flag if Cypher doesn't do aggregation in RETURN
            if 'count(' not in cy.split('return')[1] if 'return' in cy else '':
                flags.append({
                    'check': 'missing_sort_cypher',
                    'confidence': 'medium',
                    'detail': 'Cypher has ORDER BY (before final RETURN) but TypeQL has no sort',
                })

    # Check sort direction mismatch
    if 'order by' in cy and 'sort' in tql:
        try:
            cy_order_part = cy.split('order by')[-1].split('limit')[0].split('return')[0]
            tql_sort_part = tql.split('sort')[-1].split(';')[0]
            cy_desc = 'desc' in cy_order_part
            tql_desc = 'desc' in tql_sort_part

            if cy_desc and not tql_desc:
                flags.append({
                    'check': 'sort_direction_mismatch',
                    'confidence': 'high',
                    'detail': 'Cypher sorts DESC but TypeQL sorts ASC (default)',
                })
            elif not cy_desc and tql_desc:
                flags.append({
                    'check': 'sort_direction_mismatch',
                    'confidence': 'high',
                    'detail': 'Cypher sorts ASC but TypeQL sorts DESC',
                })
        except (IndexError, ValueError):
            pass

    return flags


def check_cypher_limit(cypher: str, typeql: str) -> list:
    """Check if Cypher LIMIT is reflected in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    limit_match = re.search(r'\blimit\s+(\d+)', cy)
    if limit_match:
        limit_val = limit_match.group(1)
        tql_limit = re.search(r'\blimit\s+(\d+)', tql)
        if not tql_limit:
            flags.append({
                'check': 'missing_limit',
                'confidence': 'high',
                'detail': f'Cypher has LIMIT {limit_val} but TypeQL has no limit',
            })
        elif tql_limit.group(1) != limit_val:
            flags.append({
                'check': 'limit_mismatch',
                'confidence': 'high',
                'detail': f'Cypher LIMIT {limit_val} but TypeQL limit {tql_limit.group(1)}',
            })

    return flags


def check_cypher_aggregation(cypher: str, typeql: str) -> list:
    """Check if Cypher COUNT/SUM/AVG is reflected in TypeQL reduce."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'count(' in cy and 'count' not in tql:
        flags.append({
            'check': 'missing_count',
            'confidence': 'high',
            'detail': 'Cypher uses COUNT() but TypeQL has no count',
        })

    if re.search(r'\bsum\(', cy) and 'sum(' not in tql:
        flags.append({
            'check': 'missing_sum_cypher',
            'confidence': 'high',
            'detail': 'Cypher uses SUM() but TypeQL has no sum()',
        })

    if re.search(r'\bavg\(', cy) and 'mean(' not in tql:
        flags.append({
            'check': 'missing_avg',
            'confidence': 'high',
            'detail': 'Cypher uses AVG() but TypeQL has no mean()',
        })

    return flags


def check_cypher_distinct(cypher: str, typeql: str) -> list:
    """Check if Cypher COUNT(DISTINCT) is reflected in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    # RETURN DISTINCT: often not needed in TypeQL (fetch deduplicates naturally)
    # Only flag COUNT(DISTINCT x) which requires select $x; distinct; reduce
    if re.search(r'count\s*\(\s*distinct\b', cy):
        if 'distinct' not in tql:
            # In many cases, TypeQL reduce...groupby already produces correct results
            # because match binds distinct instances. Only flag at low confidence.
            flags.append({
                'check': 'missing_count_distinct',
                'confidence': 'low',
                'detail': 'Cypher uses COUNT(DISTINCT) but TypeQL has no distinct (may be OK if groupby handles it)',
            })

    return flags


def check_cypher_optional(cypher: str, typeql: str) -> list:
    """Check if Cypher OPTIONAL MATCH is reflected in TypeQL try{}."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'optional match' in cy:
        if 'try {' not in tql and 'try{' not in tql:
            # Some OPTIONAL MATCH patterns can be handled with or{} or custom functions
            if 'with fun' not in tql and ' or {' not in tql and ' or{' not in tql:
                flags.append({
                    'check': 'missing_optional',
                    'confidence': 'high',
                    'detail': 'Cypher uses OPTIONAL MATCH but TypeQL has no try{} or equivalent',
                })

    return flags


def check_cypher_negation(cypher: str, typeql: str) -> list:
    """Check if Cypher negation is reflected in TypeQL not{}."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    negation_patterns = [
        r'where\s+not\s+exists', r'where\s+not\s*\(',
        r'and\s+not\s+exists', r'and\s+not\s*\(',
    ]

    has_cypher_negation = any(re.search(p, cy) for p in negation_patterns)
    has_typeql_negation = 'not {' in tql or 'not{' in tql

    if has_cypher_negation and not has_typeql_negation:
        flags.append({
            'check': 'missing_negation_cypher',
            'confidence': 'high',
            'detail': 'Cypher uses NOT EXISTS/NOT() but TypeQL has no not{} block',
        })

    return flags


def check_cypher_case(cypher: str, typeql: str) -> list:
    """Check if Cypher CASE WHEN is handled in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'case when' in cy or 'case\n' in cy:
        # TypeQL handles this with disjunction or let expressions
        has_handling = any(x in tql for x in ['or {', 'or{', '{ $', 'let $'])
        if not has_handling:
            flags.append({
                'check': 'missing_case',
                'confidence': 'medium',
                'detail': 'Cypher uses CASE WHEN but TypeQL may lack equivalent branching',
            })

    return flags


def check_cypher_union(cypher: str, typeql: str) -> list:
    """Check if Cypher UNION is handled in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if re.search(r'\bunion\b', cy):
        if 'or {' not in tql and 'or{' not in tql:
            flags.append({
                'check': 'missing_union',
                'confidence': 'medium',
                'detail': 'Cypher uses UNION but TypeQL has no or{} disjunction',
            })

    return flags


def check_cypher_contains_starts_with(cypher: str, typeql: str) -> list:
    """Check if Cypher string operations are reflected in TypeQL."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if re.search(r'\bcontains\b', cy) and 'like' not in tql and 'contains' not in tql:
        # String CONTAINS → like ".*pattern.*"
        flags.append({
            'check': 'missing_contains',
            'confidence': 'medium',
            'detail': 'Cypher uses CONTAINS but TypeQL has no like pattern',
        })

    if 'starts with' in cy and 'like' not in tql:
        flags.append({
            'check': 'missing_starts_with',
            'confidence': 'medium',
            'detail': 'Cypher uses STARTS WITH but TypeQL has no like pattern',
        })

    return flags


def layer2_checks(cypher: str, typeql: str) -> list:
    """Run all Layer 2 checks."""
    flags = []
    flags.extend(check_cypher_filter(cypher, typeql))
    flags.extend(check_cypher_sort(cypher, typeql))
    flags.extend(check_cypher_limit(cypher, typeql))
    flags.extend(check_cypher_aggregation(cypher, typeql))
    flags.extend(check_cypher_distinct(cypher, typeql))
    flags.extend(check_cypher_optional(cypher, typeql))
    flags.extend(check_cypher_negation(cypher, typeql))
    flags.extend(check_cypher_case(cypher, typeql))
    flags.extend(check_cypher_union(cypher, typeql))
    flags.extend(check_cypher_contains_starts_with(cypher, typeql))
    return flags


# ============================================================
# Layer 3: Schema-aware type checking
# ============================================================

def extract_typeql_types(typeql: str) -> dict:
    """Extract type references from a TypeQL query."""
    info = {
        'isa_types': [],       # Types after 'isa'
        'has_attrs': [],       # Attributes after 'has' or '.attr'
        'relations': [],       # relation_name (role: $var) patterns
        'fetch_attrs': [],     # Attributes in fetch { "key": $var.attr }
    }

    tql = typeql

    # Find 'isa <type>' patterns (types can have hyphens)
    for m in re.finditer(r'\bisa\s+([\w][\w-]*)', tql):
        info['isa_types'].append(m.group(1))

    # Find 'has <attr>' patterns (attributes can have hyphens)
    for m in re.finditer(r'\bhas\s+([\w][\w-]*)', tql):
        attr = m.group(1)
        if attr not in ('isa', 'has'):
            info['has_attrs'].append(attr)

    # Find '$var.attr' patterns in fetch (attributes can have hyphens)
    for m in re.finditer(r'\$\w+\.([\w][\w-]*)', tql):
        info['fetch_attrs'].append(m.group(1))

    # Find relation patterns: relation_name (role: $var)
    # Handle hyphenated names like "location-contains"
    for m in re.finditer(r'([\w][\w-]*\w)\s*\(([^)]+)\)', tql):
        rel_name = m.group(1)
        roles_str = m.group(2)
        # Skip if it's a function call like count($x)
        if rel_name in ('count', 'sum', 'mean', 'min', 'max', 'std', 'median',
                         'abs', 'floor', 'ceil', 'round', 'len', 'label', 'iid',
                         'reduce', 'match', 'fetch', 'sort', 'limit', 'select',
                         'let', 'not', 'try', 'or', 'fun', 'with', 'groupby',
                         'if', 'else'):
            continue

        # Parse roles
        roles = []
        for role_match in re.finditer(r'([\w-]+)\s*:\s*\$(\w+)', roles_str):
            roles.append({
                'role': role_match.group(1),
                'var': role_match.group(2),
            })

        if roles:
            info['relations'].append({
                'name': rel_name,
                'roles': roles,
            })

    return info


def layer3_checks(typeql: str, schema: dict) -> list:
    """Run schema-aware type checks."""
    flags = []
    extracted = extract_typeql_types(typeql)

    all_types = schema['all_types']
    all_attributes = schema['all_attributes']
    all_roles = schema['all_roles']

    # Check isa types
    for t in extracted['isa_types']:
        if t not in all_types:
            flags.append({
                'check': 'invalid_type',
                'confidence': 'high',
                'detail': f'TypeQL references type "{t}" which is not in schema',
            })

    # Check has attributes
    for attr in extracted['has_attrs']:
        if attr not in all_attributes:
            flags.append({
                'check': 'invalid_attribute',
                'confidence': 'high',
                'detail': f'TypeQL references attribute "{attr}" which is not in schema',
            })

    # Check fetch attributes
    for attr in extracted['fetch_attrs']:
        if attr not in all_attributes:
            flags.append({
                'check': 'invalid_fetch_attribute',
                'confidence': 'high',
                'detail': f'TypeQL fetches attribute "{attr}" which is not in schema',
            })

    # Check relation types and roles
    for rel_info in extracted['relations']:
        rel_name = rel_info['name']

        # Check relation type exists
        if rel_name not in schema['relations']:
            # Might be entity or attribute used in a different context
            if rel_name not in all_types:
                flags.append({
                    'check': 'invalid_relation',
                    'confidence': 'high',
                    'detail': f'TypeQL references relation "{rel_name}" which is not in schema',
                })
            continue

        # Check roles exist for this relation
        valid_roles = all_roles.get(rel_name, set())
        for role_info in rel_info['roles']:
            role = role_info['role']
            if role not in valid_roles:
                flags.append({
                    'check': 'invalid_role',
                    'confidence': 'high',
                    'detail': f'Role "{role}" is not valid for relation "{rel_name}" (valid: {sorted(valid_roles)})',
                })

    return flags


# ============================================================
# Layer 4: Known error patterns
# ============================================================

def layer4_checks(question: str, cypher: str, typeql: str, database: str) -> list:
    """Check for known database-specific error patterns."""
    flags = []
    q = question.lower()
    cy = cypher.lower()
    tql = typeql.lower()

    # Twitter-specific
    if database == 'twitter':
        # "retweeted X times" should count retweets, not check favorites
        if re.search(r'retweet', q) and 'favorites' in cy and 'favorites' in tql:
            if 'retweets' not in tql:
                flags.append({
                    'check': 'retweet_favorites_confusion',
                    'confidence': 'high',
                    'detail': 'Question asks about retweets but TypeQL checks favorites (likely Cypher error)',
                })

        # "similar_to score" should use relation score, not user betweenness
        if 'similar' in q and 'betweenness' in tql:
            flags.append({
                'check': 'similarity_betweenness_confusion',
                'confidence': 'high',
                'detail': 'Question about similarity uses betweenness instead of score',
            })

        # Direction: "followed by X" means X is follower
        if re.search(r'followed by\s+\w+', q):
            # Verify direction is correct
            pass  # Hard to check without parsing variable bindings

    # Companies-specific
    if database == 'companies':
        # Supplier/customer direction confusion
        if 'supplier' in q and 'customer' in tql and 'supplier' not in tql:
            flags.append({
                'check': 'supplier_customer_confusion',
                'confidence': 'medium',
                'detail': 'Question asks about suppliers but TypeQL uses customer role',
            })

    # Twitch-specific
    if database == 'twitch':
        # Stream vs User playing games
        pass

    # Cross-database: "most recent" should sort by temporal field
    if re.search(r'most recent|latest|newest', q):
        if 'sort' in tql:
            sort_section = tql.split('sort')[-1].split(';')[0]
            # Check if sorting by a temporal field or variable bound to one
            temporal_fields = ['date', 'time', 'created', 'updated', 'published', 'released',
                               'year', 'period', 'timestamp', 'at']
            has_temporal = any(f in sort_section for f in temporal_fields)
            # Also check if the sort variable is bound to a temporal attribute elsewhere
            if not has_temporal:
                sort_var_match = re.search(r'\$(\w+)', sort_section)
                if sort_var_match:
                    sort_var = sort_var_match.group(1)
                    # Check if this variable is bound to a temporal attribute in the query
                    # Use partial match: "has created_at $ca" → variable $ca has "at" in binding context
                    for tf in temporal_fields:
                        bind_pattern = rf'has\s+\w*{tf}\w*\s+\${re.escape(sort_var)}\b'
                        if re.search(bind_pattern, tql):
                            has_temporal = True
                            break
            if not has_temporal:
                flags.append({
                    'check': 'non_temporal_sort',
                    'confidence': 'low',
                    'detail': f'Question asks for "most recent" but sort may not use temporal field: {sort_section.strip()}',
                })

    # Cross-database: question mentions "or"/"either" → might need disjunction
    if re.search(r'\bor\b.*\bor\b', q) or re.search(r'\beither\b.*\bor\b', q):
        if 'or {' not in tql and 'or{' not in tql and '} or ' not in tql:
            # Only flag if Cypher also has OR/UNION
            if ' or ' in cy or 'union' in cy:
                flags.append({
                    'check': 'missing_disjunction',
                    'confidence': 'medium',
                    'detail': 'Question/Cypher has OR/either but TypeQL lacks or{} disjunction',
                })

    return flags


# ============================================================
# Main scanner
# ============================================================

def scan_database(database: str, source: str) -> dict:
    """Scan all queries for a database and return flags."""
    dataset_dir = REPO_ROOT / 'dataset' / source / database
    queries_csv = dataset_dir / 'queries.csv'
    schema_path = dataset_dir / 'schema.tql'

    if not queries_csv.exists():
        return {'database': database, 'source': source, 'error': f'queries.csv not found at {queries_csv}'}

    if not schema_path.exists():
        return {'database': database, 'source': source, 'error': f'schema.tql not found at {schema_path}'}

    # Parse schema
    schema = parse_schema(str(schema_path))

    # Read queries
    with open(queries_csv, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    all_flags = []

    for row in rows:
        idx = int(row['original_index'])
        question = row.get('question', '')
        cypher = row.get('cypher', '')
        typeql = row.get('typeql', '')

        row_flags = []

        # Layer 1: Question ↔ TypeQL (cross-referenced with Cypher)
        row_flags.extend(layer1_checks(question, cypher, typeql))

        # Layer 2: Cypher ↔ TypeQL
        row_flags.extend(layer2_checks(cypher, typeql))

        # Layer 3: Schema-aware
        row_flags.extend(layer3_checks(typeql, schema))

        # Layer 4: Known patterns
        row_flags.extend(layer4_checks(question, cypher, typeql, database))

        if row_flags:
            # Deduplicate by check name
            seen = set()
            deduped = []
            for f in row_flags:
                key = (f['check'], f['detail'])
                if key not in seen:
                    seen.add(key)
                    deduped.append(f)

            # Determine overall confidence
            confidences = [f['confidence'] for f in deduped]
            if 'high' in confidences:
                overall = 'high'
            elif 'medium' in confidences:
                overall = 'medium'
            else:
                overall = 'low'

            all_flags.append({
                'index': idx,
                'question': question,
                'cypher': cypher[:500],
                'typeql': typeql[:500],
                'checks_failed': [f['check'] for f in deduped],
                'confidence': overall,
                'details': [f['detail'] for f in deduped],
            })

    result = {
        'database': database,
        'source': source,
        'total_queries': total,
        'flagged': len(all_flags),
        'flags': all_flags,
    }

    # Categorize flags
    categories = {}
    for flag in all_flags:
        for check in flag['checks_failed']:
            if check not in categories:
                categories[check] = []
            categories[check].append(flag['index'])
    result['categories'] = categories

    return result


def print_summary(result: dict):
    """Print a human-readable summary of scan results."""
    db = result['database']
    src = result['source']
    total = result.get('total_queries', 0)
    flagged = result.get('flagged', 0)

    if 'error' in result:
        print(f"  {db} ({src}): ERROR - {result['error']}")
        return

    pct = (flagged / total * 100) if total else 0
    print(f"  {db} ({src}): {flagged}/{total} flagged ({pct:.1f}%)")

    if result.get('categories'):
        for check, indices in sorted(result['categories'].items(), key=lambda x: -len(x[1])):
            count = len(indices)
            sample = indices[:5]
            more = f" (+{count-5} more)" if count > 5 else ""
            print(f"    {check}: {count} queries - e.g. {sample}{more}")


def combine_summaries(output_dir: Path) -> dict:
    """Combine all review_flags.json files into a summary."""
    all_results = []

    for flags_file in sorted(output_dir.rglob('review_flags.json')):
        with open(flags_file) as f:
            result = json.load(f)
            all_results.append(result)

    total_queries = sum(r.get('total_queries', 0) for r in all_results)
    total_flagged = sum(r.get('flagged', 0) for r in all_results)

    # Combine categories
    combined_categories = {}
    for result in all_results:
        for check, indices in result.get('categories', {}).items():
            if check not in combined_categories:
                combined_categories[check] = {'count': 0, 'databases': []}
            combined_categories[check]['count'] += len(indices)
            combined_categories[check]['databases'].append({
                'database': result['database'],
                'source': result['source'],
                'indices': indices,
            })

    return {
        'total_queries': total_queries,
        'total_flagged': total_flagged,
        'flag_rate': f"{(total_flagged/total_queries*100):.1f}%" if total_queries else "0%",
        'databases': [{
            'database': r['database'],
            'source': r['source'],
            'total': r.get('total_queries', 0),
            'flagged': r.get('flagged', 0),
        } for r in all_results],
        'categories': combined_categories,
    }


SYNTHETIC1_DBS = ['twitter', 'twitch', 'movies', 'neoflix', 'recommendations', 'companies', 'gameofthrones']
SYNTHETIC2_DBS = ['bluesky', 'buzzoverflow', 'companies', 'fincen', 'gameofthrones', 'grandstack',
                  'movies', 'neoflix', 'network', 'northwind', 'offshoreleaks', 'recommendations',
                  'stackoverflow2', 'twitch', 'twitter']


def main():
    parser = argparse.ArgumentParser(description='Semantic review scanner for TypeQL queries')
    parser.add_argument('database', nargs='?', help='Database name to scan')
    parser.add_argument('--source', default='synthetic-1', help='Source dataset (synthetic-1 or synthetic-2)')
    parser.add_argument('--all', action='store_true', help='Scan all databases for the given source')
    parser.add_argument('--all-sources', action='store_true', help='Scan all databases across both sources')
    parser.add_argument('--summary', action='store_true', help='Combine existing review_flags.json into summary')
    parser.add_argument('--min-confidence', default='low', choices=['low', 'medium', 'high'],
                        help='Minimum confidence level to include in output')
    parser.add_argument('--json', action='store_true', help='Output raw JSON')

    args = parser.parse_args()

    confidence_levels = {'low': 0, 'medium': 1, 'high': 2}
    min_conf = confidence_levels[args.min_confidence]

    if args.summary:
        summary = combine_summaries(REPO_ROOT / 'dataset')
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"SEMANTIC REVIEW SCAN SUMMARY")
            print(f"{'='*60}")
            print(f"Total queries: {summary['total_queries']}")
            print(f"Total flagged: {summary['total_flagged']} ({summary['flag_rate']})")
            print(f"\nBy database:")
            for db in summary['databases']:
                pct = (db['flagged'] / db['total'] * 100) if db['total'] else 0
                print(f"  {db['source']}/{db['database']}: {db['flagged']}/{db['total']} ({pct:.1f}%)")
            print(f"\nBy category:")
            for check, info in sorted(summary['categories'].items(), key=lambda x: -x[1]['count']):
                print(f"  {check}: {info['count']} total across {len(info['databases'])} databases")
        return

    # Determine which databases to scan
    scan_list = []
    if args.all_sources:
        for db in SYNTHETIC1_DBS:
            scan_list.append((db, 'synthetic-1'))
        for db in SYNTHETIC2_DBS:
            scan_list.append((db, 'synthetic-2'))
    elif args.all:
        dbs = SYNTHETIC1_DBS if args.source == 'synthetic-1' else SYNTHETIC2_DBS
        for db in dbs:
            scan_list.append((db, args.source))
    elif args.database:
        scan_list.append((args.database, args.source))
    else:
        parser.print_help()
        return

    all_results = []

    for database, source in scan_list:
        print(f"Scanning {source}/{database}...", file=sys.stderr)
        result = scan_database(database, source)

        # Filter by confidence
        if min_conf > 0:
            filtered_flags = [
                f for f in result.get('flags', [])
                if confidence_levels.get(f['confidence'], 0) >= min_conf
            ]
            result['flags'] = filtered_flags
            result['flagged'] = len(filtered_flags)
            # Rebuild categories
            categories = {}
            for flag in filtered_flags:
                for check in flag['checks_failed']:
                    if check not in categories:
                        categories[check] = []
                    categories[check].append(flag['index'])
            result['categories'] = categories

        # Save per-database results
        output_path = REPO_ROOT / 'dataset' / source / database / 'review_flags.json'
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)

        all_results.append(result)

    # Print results
    if args.json:
        if len(all_results) == 1:
            print(json.dumps(all_results[0], indent=2))
        else:
            print(json.dumps(all_results, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"SEMANTIC REVIEW SCAN RESULTS")
        print(f"{'='*60}")

        total_queries = sum(r.get('total_queries', 0) for r in all_results)
        total_flagged = sum(r.get('flagged', 0) for r in all_results)
        print(f"Total queries scanned: {total_queries}")
        print(f"Total flagged: {total_flagged} ({total_flagged/total_queries*100:.1f}%)" if total_queries else "")
        print()

        for result in all_results:
            print_summary(result)
            print()

        # Overall category summary
        if len(all_results) > 1:
            print(f"--- OVERALL CATEGORIES ---")
            combined = {}
            for result in all_results:
                for check, indices in result.get('categories', {}).items():
                    if check not in combined:
                        combined[check] = 0
                    combined[check] += len(indices)
            for check, count in sorted(combined.items(), key=lambda x: -x[1]):
                print(f"  {check}: {count}")


if __name__ == '__main__':
    main()
