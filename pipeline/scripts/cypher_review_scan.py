#!/usr/bin/env python3
"""Automated Cypher correctness scanner for converted query triples.

Uses English questions + validated TypeQL as ground truth to check whether
the original Cypher queries are semantically correct.

Scans (question, cypher, typeql) triples across 4 layers:
  Layer 1: Question → Cypher structural checks
  Layer 2: Question → Cypher semantic checks
  Layer 3: Neo4j schema validation
  Layer 4: TypeQL cross-reference (Cypher vs corrected TypeQL)

Usage:
  python3 pipeline/scripts/cypher_review_scan.py <database> --source <synthetic-1|synthetic-2>
  python3 pipeline/scripts/cypher_review_scan.py --all --source synthetic-1
  python3 pipeline/scripts/cypher_review_scan.py --all-sources
  python3 pipeline/scripts/cypher_review_scan.py --summary  # combine existing cypher_flags.json
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
# Neo4j schema parser
# ============================================================

def parse_neo4j_schema(path: str) -> dict:
    """Parse a Neo4j schema JSON file into structured data.

    Returns:
        {
            'node_labels': set of label names,
            'node_props': {label: {prop_name: prop_type}},
            'rel_types': set of relationship type names,
            'rel_props': {rel_type: {prop_name: prop_type}},
            'relationships': [(start_label, rel_type, end_label), ...],
            'rel_directions': {rel_type: [(start, end), ...]},
        }
    """
    with open(path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    node_labels = set()
    node_props = {}
    for label, props in schema.get('node_props', {}).items():
        node_labels.add(label)
        node_props[label] = {}
        for p in props:
            node_props[label][p['property']] = p.get('type', 'STRING')

    rel_types = set()
    rel_props = {}
    for rtype, props in schema.get('rel_props', {}).items():
        rel_types.add(rtype)
        rel_props[rtype] = {}
        for p in props:
            rel_props[rtype][p['property']] = p.get('type', 'STRING')

    relationships = []
    rel_directions = {}
    for r in schema.get('relationships', []):
        start = r['start']
        rtype = r['type']
        end = r['end']
        node_labels.add(start)
        node_labels.add(end)
        rel_types.add(rtype)
        relationships.append((start, rtype, end))
        if rtype not in rel_directions:
            rel_directions[rtype] = []
        rel_directions[rtype].append((start, end))

    # All properties across all labels
    all_props = set()
    for label_props in node_props.values():
        all_props.update(label_props.keys())
    for rtype_props in rel_props.values():
        all_props.update(rtype_props.keys())

    return {
        'node_labels': node_labels,
        'node_props': node_props,
        'rel_types': rel_types,
        'rel_props': rel_props,
        'relationships': relationships,
        'rel_directions': rel_directions,
        'all_props': all_props,
    }


# ============================================================
# Cypher extraction utilities
# ============================================================

def extract_cypher_labels(cypher: str) -> set:
    """Extract :Label references from node patterns in Cypher.

    Matches patterns like (n:User), (:Tweet), (n:User:Admin).
    Does NOT match relationship types in [:REL_TYPE].
    """
    labels = set()

    # Match node patterns: (var:Label) or (:Label) or (var:Label {props})
    # Key: labels appear after : inside parentheses (...), NOT brackets [...]
    # Patterns: (var:Label), (:Label), (var:Label:Label2), (var:Label {key: val})
    for m in re.finditer(r'\(\s*\w*\s*:([\w]+(?::[\w]+)*)', cypher):
        for label in m.group(1).split(':'):
            if label:
                labels.add(label)

    return labels


def extract_cypher_rel_types(cypher: str) -> set:
    """Extract [:REL_TYPE] references from Cypher."""
    rel_types = set()
    # Match relationship type patterns: [:TYPE], [r:TYPE], [:TYPE*], [:TYPE|OTHER]
    for m in re.finditer(r'\[\s*\w*\s*:([\w|]+)', cypher):
        for rtype in m.group(1).split('|'):
            rtype = rtype.strip()
            if rtype:
                rel_types.add(rtype)
    return rel_types


def extract_cypher_properties(cypher: str) -> list:
    """Extract var.property pairs from Cypher.

    Returns list of (variable, property) tuples.
    """
    props = []
    for m in re.finditer(r'\b(\w+)\.([\w]+)\b', cypher):
        var = m.group(1)
        prop = m.group(2)
        # Filter out Cypher keywords and function-like patterns
        if var.upper() not in (
            'MATCH', 'WHERE', 'RETURN', 'WITH', 'ORDER', 'LIMIT', 'SKIP',
            'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'AND', 'OR', 'NOT',
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COLLECT', 'DISTINCT',
            'OPTIONAL', 'UNWIND', 'MERGE', 'CREATE', 'DELETE', 'SET',
            'CALL', 'YIELD', 'EXISTS', 'KEYS', 'LABELS', 'TYPE',
        ):
            props.append((var, prop))
    return props


def extract_cypher_var_labels(cypher: str) -> dict:
    """Map Cypher variables to their labels.

    Parses patterns like (u:User), (t:Tweet {id: 123}).
    Returns {variable: label}.
    """
    var_labels = {}
    # Match (var:Label ...) patterns
    for m in re.finditer(r'\(\s*(\w+)\s*:([\w]+)', cypher):
        var = m.group(1)
        label = m.group(2)
        var_labels[var] = label
    return var_labels


def neo4j_to_typeql_name(name: str) -> str:
    """Convert PascalCase/UPPER_CASE Neo4j name to snake_case TypeQL name.

    Examples:
        User -> user
        FOLLOWS -> follows
        INTERACTS_WITH -> interacts-with  (or interacts_with)
        HAS_CEO -> has-ceo
        Tweet -> tweet
    """
    if name.isupper() or '_' in name:
        # UPPER_CASE or UPPER_SNAKE_CASE -> lower with hyphens
        return name.lower().replace('_', '-')
    else:
        # PascalCase -> snake_case
        s = re.sub(r'([A-Z])', r'_\1', name).lstrip('_').lower()
        return s


# ============================================================
# Helper: parse numbers from question text
# ============================================================

def _parse_question_number(text: str, start: int) -> int | None:
    """Parse a number from question text, handling commas and magnitude words."""
    m = re.match(r'(\d[\d,]*\d|\d)', text[start:])
    if m:
        num_str = m.group(1).replace(',', '')
        remaining = text[start + m.end():].strip()
        magnitudes = {'thousand': 1_000, 'million': 1_000_000, 'billion': 1_000_000_000}
        for word, mult in magnitudes.items():
            if remaining.startswith(word):
                return int(num_str) * mult
        return int(num_str)
    return None


# ============================================================
# Layer 1: Question → Cypher structural checks
# ============================================================

def check_missing_count(question: str, cypher: str) -> list:
    """Question asks 'how many' but Cypher lacks COUNT()."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    count_patterns = [
        r'\bhow many\b', r'\btotal number\b', r'\bnumber of\b',
    ]
    needs_count = any(re.search(p, q) for p in count_patterns)
    has_count = 'count(' in cy

    if needs_count and not has_count:
        # Exception: question might be answered by a property rather than COUNT()
        # e.g., "how many followers" -> u.followers, "number of statuses" -> u.statuses
        # Check if Cypher returns a property that could represent a count
        property_count_words = [
            'followers', 'following', 'statuses', 'friends', 'favorites',
            'views', 'subscribers', 'connections', 'likes', 'votes',
            'reviews', 'ratings', 'episodes', 'seasons', 'quantity',
            'units', 'stock', 'count', 'total', 'amount', 'size',
        ]
        answered_by_property = False
        for word in property_count_words:
            if word in q:
                # Check if Cypher accesses this as a property
                if re.search(rf'\.{word}\b', cy) or re.search(rf'\.{word}s?\b', cy):
                    answered_by_property = True
                    break
                # Also check: "number of X" where X is returned via .X property
                if re.search(rf'\bnumber of {word}\b', q) or re.search(rf'\bhow many {word}\b', q):
                    answered_by_property = True
                    break

        # Also skip if question has "number of" / "highest number" followed by a property name
        # and Cypher accesses that property with dot notation
        if not answered_by_property:
            prop_match = re.search(r'(?:number of|how many)\s+(\w+)', q)
            if prop_match:
                prop_word = prop_match.group(1)
                if re.search(rf'\.{re.escape(prop_word)}\b', cy):
                    answered_by_property = True

        if not answered_by_property:
            flags.append({
                'check': 'cypher_missing_count',
                'confidence': 'high',
                'detail': 'Question asks "how many" but Cypher has no COUNT()',
            })

    return flags


def check_missing_avg(question: str, cypher: str) -> list:
    """Question asks 'average' but Cypher lacks avg()."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    if re.search(r'\baverage\b|\bmean\b|\bavg\b', q):
        # Skip if "average" is part of an attribute name
        if re.search(r'\baverage[_\s](?:vote|rating|score)\b', q) and 'avg(' not in cy:
            # Could be a property name, not a computation request
            pass
        elif 'avg(' not in cy:
            flags.append({
                'check': 'cypher_missing_avg',
                'confidence': 'high',
                'detail': 'Question asks for average but Cypher has no avg()',
            })

    return flags


def check_missing_sum(question: str, cypher: str) -> list:
    """Question asks 'total revenue'/'sum of' but Cypher lacks sum()."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    if re.search(r'\btotal\s+(?:revenue|amount|value|price|cost|sales|quantity|freight|discount|weight)\b|\bsum\s+of\b', q):
        if 'sum(' not in cy:
            flags.append({
                'check': 'cypher_missing_sum',
                'confidence': 'medium',
                'detail': 'Question asks for total/sum but Cypher has no sum()',
            })

    return flags


def check_missing_order_limit(question: str, cypher: str) -> list:
    """Question asks 'top N' but Cypher lacks ORDER BY + LIMIT."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    # Ranked patterns
    ranked_patterns = [
        r'\btop\s+(\d+)\b',
        r'\b(\d+)\s+most\b', r'\b(\d+)\s+least\b',
        r'\b(\d+)\s+highest\b', r'\b(\d+)\s+lowest\b',
        r'\b(\d+)\s+biggest\b', r'\b(\d+)\s+smallest\b',
        r'\b(\d+)\s+largest\b',
    ]

    for pattern in ranked_patterns:
        m = re.search(pattern, q)
        if m:
            n = m.group(1)
            has_order = 'order by' in cy
            has_limit = re.search(rf'\blimit\s+{n}\b', cy)

            if not has_order:
                flags.append({
                    'check': 'cypher_missing_order',
                    'confidence': 'high',
                    'detail': f'Question asks for top-{n} but Cypher has no ORDER BY',
                })
            if not has_limit:
                flags.append({
                    'check': 'cypher_missing_limit',
                    'confidence': 'high',
                    'detail': f'Question asks for top-{n} but Cypher has no LIMIT {n}',
                })
            break

    # Single superlative: "most popular", "highest rated" -> need ORDER BY...LIMIT 1
    superlative_patterns = [
        r'\bmost\s+\w+\b', r'\bhighest\b', r'\blowest\b',
        r'\blargest\b', r'\bsmallest\b', r'\bbiggest\b',
        r'\boldest\b', r'\bnewest\b', r'\byoungest\b',
        r'\bmost\s+recent\b', r'\bearliest\b', r'\blatest\b',
    ]

    for pattern in superlative_patterns:
        sm = re.search(pattern, q)
        if sm:
            has_order = 'order by' in cy
            has_maxmin = 'max(' in cy or 'min(' in cy

            if not has_order and not has_maxmin:
                # Only flag if it's not already caught by top-N
                if not re.search(r'\btop\s+\d+\b', q):
                    flags.append({
                        'check': 'cypher_missing_order_superlative',
                        'confidence': 'medium',
                        'detail': f'Question uses superlative "{sm.group()}" but Cypher has no ORDER BY or max/min',
                    })
            break

    return flags


def check_missing_negation(question: str, cypher: str) -> list:
    """Question implies 'not'/'never'/'without' but Cypher lacks NOT/WHERE NOT."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    negation_patterns = [
        r"\bwho\s+(?:have|has)\s+not\b",
        r"\bwho\s+(?:don't|doesn't|do not|does not)\b",
        r"\bthat\s+(?:don't|doesn't|do not|does not)\b",
        r"\bnever\b",
        r"\bwithout\s+(?:any|a)\b",
        r"\bno\s+(?:followers|following|tweets|movies|reviews|orders|connections|friends)\b",
        r"\bnot\s+(?:followed|following|connected|linked|related|acted|directed|written|posted|reviewed)\b",
        r"\bhave\s+not\s+(?:been|made|written|posted|reviewed|directed|acted)\b",
    ]

    needs_negation = any(re.search(p, q) for p in negation_patterns)
    has_negation = any(x in cy for x in [
        'not exists', 'not (', 'where not', 'and not',
        'is null', '= false', '= 0',
    ])

    if needs_negation and not has_negation:
        flags.append({
            'check': 'cypher_missing_negation',
            'confidence': 'medium',
            'detail': 'Question implies negation but Cypher has no NOT/WHERE NOT/IS NULL',
        })

    return flags


def check_missing_contains(question: str, cypher: str) -> list:
    """Question implies substring search but Cypher lacks CONTAINS/STARTS WITH."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    # Patterns suggesting substring matching
    contains_patterns = [
        r'\bcontain(?:s|ing)?\b',
        r'\binclud(?:e|es|ing)\b.*\b(?:word|text|name|term)\b',
        r'\bmentions?\s+(?:the\s+)?(?:word|term|phrase)\b',
        r'\bwith\s+[\"\'].+[\"\'].*\bin\s+(?:their|the|its)\b',
    ]

    needs_contains = any(re.search(p, q) for p in contains_patterns)
    has_contains = any(x in cy for x in ['contains', 'starts with', 'ends with', '=~'])

    if needs_contains and not has_contains:
        # Skip if the question might mean "contain" as in "have" (e.g., "tweets that contain links")
        # Only flag when it clearly means substring
        if re.search(r'\bcontain(?:s|ing)?\s+(?:the\s+)?(?:word|text|string|term|phrase|letter|character)', q):
            flags.append({
                'check': 'cypher_missing_contains',
                'confidence': 'medium',
                'detail': 'Question implies substring search but Cypher has no CONTAINS/regex',
            })

    return flags


def check_missing_threshold(question: str, cypher: str) -> list:
    """Question says 'more than 100' but number is absent from Cypher."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

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
                if not re.search(rf'\b{num_str}\b', cy):
                    # Skip years
                    if 1900 <= parsed <= 2100:
                        continue
                    flags.append({
                        'check': 'cypher_missing_threshold',
                        'confidence': 'high',
                        'detail': f'Question mentions threshold {num_str} but it does not appear in Cypher',
                    })

    return flags


def check_missing_distinct(question: str, cypher: str) -> list:
    """Question says 'distinct'/'unique' but Cypher lacks DISTINCT."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    if re.search(r'\bdistinct\b|\bunique\b', q):
        if 'distinct' not in cy:
            flags.append({
                'check': 'cypher_missing_distinct',
                'confidence': 'low',
                'detail': 'Question asks for distinct/unique but Cypher has no DISTINCT',
            })

    return flags


def layer1_checks(question: str, cypher: str) -> list:
    """Run all Layer 1: Question → Cypher structural checks."""
    flags = []
    flags.extend(check_missing_count(question, cypher))
    flags.extend(check_missing_avg(question, cypher))
    flags.extend(check_missing_sum(question, cypher))
    flags.extend(check_missing_order_limit(question, cypher))
    flags.extend(check_missing_negation(question, cypher))
    flags.extend(check_missing_contains(question, cypher))
    flags.extend(check_missing_threshold(question, cypher))
    flags.extend(check_missing_distinct(question, cypher))
    return flags


# ============================================================
# Layer 2: Question → Cypher semantic checks
# ============================================================

def check_return_entity_mismatch(question: str, cypher: str) -> list:
    """Question's subject entity doesn't match what Cypher returns."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    # Only check patterns where the entity is clearly the SUBJECT of the question
    # (at the beginning, or right after "which/find/list/show")
    # Avoid matching entities in subordinate clauses ("tweets THAT mention ...")
    entity_subject_patterns = {
        'user': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?users?\b',
                 r'^who\s+are\s+the\s+users?\b'],
        'tweet': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?tweets?\b'],
        'movie': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?movies?\b'],
        'person': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?(?:people|persons?|actors?|directors?)\b'],
        'company': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?companies\b'],
        'product': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?products?\b'],
        'order': [r'^(?:which|find|list|show|get|identify|display)\s+(?:all\s+)?(?:the\s+)?orders?\b'],
    }

    # Check what the question's SUBJECT entity is
    asked_entity = None
    for entity, patterns in entity_subject_patterns.items():
        if any(re.search(p, q) for p in patterns):
            asked_entity = entity
            break

    if not asked_entity:
        return flags

    # Check what Cypher returns (extract from RETURN clause)
    return_match = re.search(r'\breturn\s+(.+?)(?:\s+order\s|\s+limit\s|\s+skip\s|$)', cy, re.DOTALL)
    if not return_match:
        return flags

    return_clause = return_match.group(1).strip()
    var_labels = extract_cypher_var_labels(cypher)

    # Check each returned variable
    returned_labels = set()
    for var in re.findall(r'\b(\w+)(?:\.\w+)?', return_clause):
        if var in var_labels:
            returned_labels.add(var_labels[var].lower())

    if not returned_labels:
        return flags

    # Check if any returned label matches the asked entity
    entity_label_map = {
        'user': {'user', 'me', 'person', 'customer', 'employee', 'member'},
        'tweet': {'tweet', 'post', 'message'},
        'movie': {'movie', 'film'},
        'person': {'person', 'actor', 'director', 'user', 'customer', 'employee'},
        'company': {'company', 'organization', 'org'},
        'product': {'product', 'item'},
        'order': {'order', 'purchase'},
    }

    expected_labels = entity_label_map.get(asked_entity, {asked_entity})
    if returned_labels and not returned_labels.intersection(expected_labels):
        flags.append({
            'check': 'cypher_return_entity_mismatch',
            'confidence': 'medium',
            'detail': f'Question asks about {asked_entity}s but Cypher returns {sorted(returned_labels)}',
        })

    return flags


def check_multiple_conditions(question: str, cypher: str) -> list:
    """Question says 'both X and Y' but Cypher has only one condition."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    # "both X and Y"
    both_match = re.search(r'\bboth\s+(.+?)\s+and\s+(.+?)(?:\?|$|,)', q)
    if both_match:
        cond1 = both_match.group(1).strip()
        cond2 = both_match.group(2).strip()

        # Check if WHERE clause has AND
        where_match = re.search(r'\bwhere\s+(.+?)(?:\breturn\b|\bwith\b|\border\b|$)', cy, re.DOTALL)
        if where_match:
            where_clause = where_match.group(1)
            if ' and ' not in where_clause:
                flags.append({
                    'check': 'cypher_missing_condition',
                    'confidence': 'medium',
                    'detail': f'Question requires "both...and" but Cypher WHERE lacks AND',
                })

    # "X and Y" with two clearly different properties
    # This is more nuanced, skip for now to avoid false positives

    return flags


def check_missing_returned_properties(question: str, cypher: str) -> list:
    """Question asks for 'name and email' but Cypher only returns one."""
    flags = []
    q = question.lower()
    cy = cypher.lower()

    # Look for explicit "X and Y" property requests
    prop_request = re.search(
        r'(?:return|show|display|get|list|give|provide|include)\s+(?:their|the|each)?\s*'
        r'(\w+)\s+and\s+(\w+)',
        q
    )
    if prop_request:
        prop1 = prop_request.group(1)
        prop2 = prop_request.group(2)

        # Check RETURN clause
        return_match = re.search(r'\breturn\s+(.+?)(?:\s+order\s|\s+limit\s|\s+skip\s|$)', cy, re.DOTALL)
        if return_match:
            return_clause = return_match.group(1).lower()
            if prop1 not in return_clause and prop2 not in return_clause:
                flags.append({
                    'check': 'cypher_missing_return_props',
                    'confidence': 'medium',
                    'detail': f'Question asks for "{prop1} and {prop2}" but neither appears in RETURN',
                })
            elif prop1 not in return_clause:
                flags.append({
                    'check': 'cypher_missing_return_prop',
                    'confidence': 'medium',
                    'detail': f'Question asks for "{prop1}" but it does not appear in RETURN',
                })
            elif prop2 not in return_clause:
                flags.append({
                    'check': 'cypher_missing_return_prop',
                    'confidence': 'medium',
                    'detail': f'Question asks for "{prop2}" but it does not appear in RETURN',
                })

    return flags


def layer2_checks(question: str, cypher: str) -> list:
    """Run all Layer 2: Question → Cypher semantic checks."""
    flags = []
    flags.extend(check_return_entity_mismatch(question, cypher))
    flags.extend(check_multiple_conditions(question, cypher))
    flags.extend(check_missing_returned_properties(question, cypher))
    return flags


# ============================================================
# Layer 3: Neo4j schema validation
# ============================================================

def check_invalid_labels(cypher: str, neo4j_schema: dict) -> list:
    """Cypher references non-existent node labels."""
    flags = []
    labels = extract_cypher_labels(cypher)
    valid_labels = neo4j_schema['node_labels']

    for label in labels:
        if label not in valid_labels:
            # Check case-insensitive
            if not any(label.lower() == vl.lower() for vl in valid_labels):
                flags.append({
                    'check': 'cypher_invalid_label',
                    'confidence': 'high',
                    'detail': f'Cypher references label "{label}" not in Neo4j schema (valid: {sorted(valid_labels)})',
                })

    return flags


def check_invalid_rel_types(cypher: str, neo4j_schema: dict) -> list:
    """Cypher references non-existent relationship types."""
    flags = []
    rel_types = extract_cypher_rel_types(cypher)
    valid_types = neo4j_schema['rel_types']

    for rtype in rel_types:
        if rtype not in valid_types:
            # Check case-insensitive
            if not any(rtype.lower() == vt.lower() for vt in valid_types):
                flags.append({
                    'check': 'cypher_invalid_rel_type',
                    'confidence': 'high',
                    'detail': f'Cypher references relationship type "{rtype}" not in Neo4j schema (valid: {sorted(valid_types)})',
                })

    return flags


def check_invalid_properties(cypher: str, neo4j_schema: dict) -> list:
    """Cypher accesses properties not defined for that label."""
    flags = []
    var_labels = extract_cypher_var_labels(cypher)
    props = extract_cypher_properties(cypher)

    for var, prop in props:
        if var in var_labels:
            label = var_labels[var]
            label_props = neo4j_schema['node_props'].get(label, {})
            if label_props and prop not in label_props:
                # Check if it's a relationship property
                if prop not in neo4j_schema.get('all_props', set()):
                    flags.append({
                        'check': 'cypher_invalid_property',
                        'confidence': 'high',
                        'detail': f'Cypher accesses {var}.{prop} but "{prop}" is not a property of :{label} (valid: {sorted(label_props.keys())})',
                    })
                else:
                    flags.append({
                        'check': 'cypher_wrong_label_property',
                        'confidence': 'medium',
                        'detail': f'Cypher accesses {var}.{prop} but "{prop}" is not on :{label} (exists on other types)',
                    })

    return flags


def check_relationship_direction(cypher: str, neo4j_schema: dict) -> list:
    """Cypher direction doesn't match schema's (start→end)."""
    flags = []
    var_labels = extract_cypher_var_labels(cypher)
    rel_directions = neo4j_schema['rel_directions']

    # Parse directed relationship patterns:
    # (a)-[:TYPE]->(b) or (a)<-[:TYPE]-(b)
    dir_patterns = [
        # (a)-[:TYPE]->(b) — a is start, b is end
        (r'\(\s*(\w+)\s*(?::[\w]+)?\s*\)\s*-\s*\[\s*\w*\s*:([\w]+)\s*\]\s*->\s*\(\s*(\w+)', 'forward'),
        # (a)<-[:TYPE]-(b) — b is start, a is end
        (r'\(\s*(\w+)\s*(?::[\w]+)?\s*\)\s*<-\s*\[\s*\w*\s*:([\w]+)\s*\]\s*-\s*\(\s*(\w+)', 'backward'),
    ]

    for pattern, direction in dir_patterns:
        for m in re.finditer(pattern, cypher):
            var_a = m.group(1)
            rtype = m.group(2)
            var_b = m.group(3)

            if rtype not in rel_directions:
                continue

            label_a = var_labels.get(var_a)
            label_b = var_labels.get(var_b)

            if not label_a or not label_b:
                continue

            # Determine expected direction
            if direction == 'forward':
                cypher_start, cypher_end = label_a, label_b
            else:
                cypher_start, cypher_end = label_b, label_a

            # Check if this direction exists in schema
            valid_dirs = rel_directions[rtype]
            match = any(
                (s == cypher_start or s.lower() == cypher_start.lower()) and
                (e == cypher_end or e.lower() == cypher_end.lower())
                for s, e in valid_dirs
            )

            if not match:
                # Check reverse direction
                reverse_match = any(
                    (s == cypher_end or s.lower() == cypher_end.lower()) and
                    (e == cypher_start or e.lower() == cypher_start.lower())
                    for s, e in valid_dirs
                )
                if reverse_match:
                    flags.append({
                        'check': 'cypher_wrong_direction',
                        'confidence': 'high',
                        'detail': f'Cypher has ({label_a})-[:{rtype}]->({label_b}) but schema says {label_b}->{label_a}',
                    })

    return flags


def layer3_checks(cypher: str, neo4j_schema: dict) -> list:
    """Run all Layer 3: Neo4j schema validation."""
    flags = []
    flags.extend(check_invalid_labels(cypher, neo4j_schema))
    flags.extend(check_invalid_rel_types(cypher, neo4j_schema))
    flags.extend(check_invalid_properties(cypher, neo4j_schema))
    flags.extend(check_relationship_direction(cypher, neo4j_schema))
    return flags


# ============================================================
# Layer 4: TypeQL cross-reference
# ============================================================

def extract_typeql_types(typeql: str) -> dict:
    """Extract type references from a TypeQL query (reused from semantic_review_scan)."""
    info = {
        'isa_types': [],
        'has_attrs': [],
        'relations': [],
        'fetch_attrs': [],
    }
    tql = typeql

    for m in re.finditer(r'\bisa\s+([\w][\w-]*)', tql):
        info['isa_types'].append(m.group(1))

    for m in re.finditer(r'\bhas\s+([\w][\w-]*)', tql):
        attr = m.group(1)
        if attr not in ('isa', 'has'):
            info['has_attrs'].append(attr)

    for m in re.finditer(r'\$\w+\.([\w][\w-]*)', tql):
        info['fetch_attrs'].append(m.group(1))

    for m in re.finditer(r'([\w][\w-]*\w)\s*\(([^)]+)\)', tql):
        rel_name = m.group(1)
        roles_str = m.group(2)
        if rel_name in ('count', 'sum', 'mean', 'min', 'max', 'std', 'median',
                         'abs', 'floor', 'ceil', 'round', 'len', 'label', 'iid',
                         'reduce', 'match', 'fetch', 'sort', 'limit', 'select',
                         'let', 'not', 'try', 'or', 'fun', 'with', 'groupby',
                         'if', 'else'):
            continue
        roles = []
        for role_match in re.finditer(r'([\w-]+)\s*:\s*\$(\w+)', roles_str):
            roles.append({'role': role_match.group(1), 'var': role_match.group(2)})
        if roles:
            info['relations'].append({'name': rel_name, 'roles': roles})

    return info


def check_typeql_has_count_cypher_lacks(cypher: str, typeql: str) -> list:
    """TypeQL has reduce...count but Cypher lacks COUNT()."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'reduce' in tql and 'count' in tql:
        # Cypher count can appear as COUNT(...) or count{...} (subquery count)
        has_cypher_count = 'count(' in cy or 'count{' in cy or 'count {' in cy
        if not has_cypher_count:
            flags.append({
                'check': 'cypher_lacks_count_vs_typeql',
                'confidence': 'high',
                'detail': 'TypeQL uses reduce...count but Cypher has no COUNT()',
            })

    return flags


def check_typeql_has_sort_cypher_lacks(cypher: str, typeql: str) -> list:
    """TypeQL has sort but Cypher lacks ORDER BY."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'sort' in tql and 'order by' not in cy:
        flags.append({
            'check': 'cypher_lacks_sort_vs_typeql',
            'confidence': 'medium',
            'detail': 'TypeQL uses sort but Cypher has no ORDER BY',
        })

    return flags


def check_typeql_has_negation_cypher_lacks(cypher: str, typeql: str) -> list:
    """TypeQL has not{} but Cypher lacks NOT."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    has_typeql_negation = 'not {' in tql or 'not{' in tql
    has_cypher_negation = any(x in cy for x in [
        'not exists', 'not (', 'where not', 'and not', 'is null',
    ])

    if has_typeql_negation and not has_cypher_negation:
        flags.append({
            'check': 'cypher_lacks_negation_vs_typeql',
            'confidence': 'high',
            'detail': 'TypeQL uses not{} but Cypher has no negation',
        })

    return flags


def check_typeql_has_like_cypher_lacks(cypher: str, typeql: str) -> list:
    """TypeQL has like but Cypher lacks CONTAINS/STARTS WITH."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    if 'like' in tql and 'like' not in cy:
        has_cypher_string_op = any(x in cy for x in [
            'contains', 'starts with', 'ends with', '=~',
        ])
        if not has_cypher_string_op:
            flags.append({
                'check': 'cypher_lacks_string_op_vs_typeql',
                'confidence': 'medium',
                'detail': 'TypeQL uses like pattern but Cypher has no CONTAINS/STARTS WITH/regex',
            })

    return flags


def check_typeql_different_entity(cypher: str, typeql: str, typeql_schema: dict = None) -> list:
    """TypeQL uses a different main entity type than Cypher."""
    flags = []
    tql = typeql.lower()

    # Extract primary types from Cypher and TypeQL
    cypher_labels = set()
    for m in re.finditer(r'\(\s*\w+\s*:([\w]+)', cypher):
        cypher_labels.add(m.group(1).lower())

    typeql_types = set()
    for m in re.finditer(r'\bisa\s+([\w][\w-]*)', tql):
        typeql_types.add(m.group(1).lower())

    # Also extract types referenced through relations (not just isa)
    for m in re.finditer(r'([\w][\w-]*)\s*\([^)]*:', tql):
        name = m.group(1)
        if name not in ('count', 'sum', 'mean', 'min', 'max', 'std', 'median',
                         'abs', 'floor', 'ceil', 'round', 'len', 'label', 'iid',
                         'reduce', 'match', 'fetch', 'sort', 'limit', 'select',
                         'let', 'not', 'try', 'or', 'fun', 'with', 'groupby',
                         'if', 'else'):
            typeql_types.add(name)

    if not cypher_labels or not typeql_types:
        return flags

    # Build subtype mapping (child -> ancestors including self)
    subtypes = {}
    if typeql_schema:
        for child, parent in typeql_schema.get('subtypes', {}).items():
            chain = {child.lower(), parent.lower()}
            # Follow chain up
            p = parent
            while p in typeql_schema.get('subtypes', {}):
                p = typeql_schema['subtypes'][p]
                chain.add(p.lower())
            subtypes[child.lower()] = chain

    # Normalize all names for comparison
    cypher_normalized = set()
    for label in cypher_labels:
        cypher_normalized.add(label)
        cypher_normalized.add(neo4j_to_typeql_name(label))
        cypher_normalized.add(label.replace('_', '-'))

    typeql_expanded = set()
    for t in typeql_types:
        typeql_expanded.add(t)
        typeql_expanded.add(t.replace('-', '_'))
        # Add parent types from subtype chain
        if t in subtypes:
            typeql_expanded.update(subtypes[t])
            for st in subtypes[t]:
                typeql_expanded.add(st.replace('-', '_'))

    # Check if at least one Cypher label is matched in TypeQL
    # Use both exact matching and substring matching to handle naming convention differences
    # e.g., Cypher "Entity" -> TypeQL "offshore_entity" (contains "entity")
    matched = False
    for label in cypher_labels:
        tql_name = neo4j_to_typeql_name(label)
        # Exact match
        if (tql_name in typeql_expanded or
            label.lower() in typeql_expanded or
            label.replace('_', '-').lower() in typeql_expanded):
            matched = True
            break
        # Substring match: Cypher label appears as substring of a TypeQL type
        for tql_type in typeql_expanded:
            if (tql_name in tql_type or label.lower() in tql_type or
                tql_type in tql_name or tql_type in label.lower()):
                matched = True
                break
        if matched:
            break

    if not matched:
        # Cypher uses labels not found in TypeQL at all — significant
        flags.append({
            'check': 'cypher_typeql_entity_mismatch',
            'confidence': 'low',
            'detail': f'Cypher labels {sorted(cypher_labels)} may not match TypeQL types {sorted(typeql_types)}',
        })

    return flags


def check_typeql_has_optional_cypher_lacks(cypher: str, typeql: str) -> list:
    """TypeQL uses try{}/custom function but Cypher lacks OPTIONAL MATCH."""
    flags = []
    cy = cypher.lower()
    tql = typeql.lower()

    has_typeql_optional = 'try {' in tql or 'try{' in tql or 'with fun' in tql
    has_cypher_optional = 'optional match' in cy

    if has_typeql_optional and not has_cypher_optional:
        flags.append({
            'check': 'cypher_lacks_optional_vs_typeql',
            'confidence': 'medium',
            'detail': 'TypeQL uses try{}/custom function but Cypher has no OPTIONAL MATCH',
        })

    return flags


def layer4_checks(cypher: str, typeql: str, typeql_schema: dict = None) -> list:
    """Run all Layer 4: TypeQL cross-reference checks."""
    flags = []
    flags.extend(check_typeql_has_count_cypher_lacks(cypher, typeql))
    flags.extend(check_typeql_has_sort_cypher_lacks(cypher, typeql))
    flags.extend(check_typeql_has_negation_cypher_lacks(cypher, typeql))
    flags.extend(check_typeql_has_like_cypher_lacks(cypher, typeql))
    # Note: check_typeql_different_entity disabled — too many false positives
    # due to naming convention differences between Neo4j labels and TypeQL types
    # (e.g., Actor→person, Entity→offshore_entity, Stream→stream via relations)
    flags.extend(check_typeql_has_optional_cypher_lacks(cypher, typeql))
    return flags


# ============================================================
# Main scanner
# ============================================================

def scan_database(database: str, source: str) -> dict:
    """Scan all queries for a database and return Cypher flags."""
    dataset_dir = REPO_ROOT / 'dataset' / source / database
    queries_csv = dataset_dir / 'queries.csv'
    neo4j_schema_path = dataset_dir / 'neo4j_schema.json'

    if not queries_csv.exists():
        return {'database': database, 'source': source, 'error': f'queries.csv not found at {queries_csv}'}

    # Parse Neo4j schema (optional — Layer 3 skipped if missing)
    neo4j_schema = None
    if neo4j_schema_path.exists():
        try:
            neo4j_schema = parse_neo4j_schema(str(neo4j_schema_path))
        except Exception as e:
            print(f"  Warning: could not parse Neo4j schema: {e}", file=sys.stderr)

    # Parse TypeQL schema (optional — used for subtype info in Layer 4)
    typeql_schema_path = dataset_dir / 'schema.tql'
    typeql_schema = None
    if typeql_schema_path.exists():
        try:
            typeql_schema = parse_schema(str(typeql_schema_path))
        except Exception as e:
            print(f"  Warning: could not parse TypeQL schema: {e}", file=sys.stderr)

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

        # Layer 1: Question → Cypher structural checks
        row_flags.extend(layer1_checks(question, cypher))

        # Layer 2: Question → Cypher semantic checks
        row_flags.extend(layer2_checks(question, cypher))

        # Layer 3: Neo4j schema validation
        if neo4j_schema:
            row_flags.extend(layer3_checks(cypher, neo4j_schema))

        # Layer 4: TypeQL cross-reference
        row_flags.extend(layer4_checks(cypher, typeql, typeql_schema))

        if row_flags:
            # Deduplicate by (check, detail)
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
    """Combine all cypher_flags.json files into a summary."""
    all_results = []

    for flags_file in sorted(output_dir.rglob('cypher_flags.json')):
        with open(flags_file) as f:
            result = json.load(f)
            all_results.append(result)

    total_queries = sum(r.get('total_queries', 0) for r in all_results)
    total_flagged = sum(r.get('flagged', 0) for r in all_results)

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
    parser = argparse.ArgumentParser(description='Cypher correctness scanner for converted query triples')
    parser.add_argument('database', nargs='?', help='Database name to scan')
    parser.add_argument('--source', default='synthetic-1', help='Source dataset (synthetic-1 or synthetic-2)')
    parser.add_argument('--all', action='store_true', help='Scan all databases for the given source')
    parser.add_argument('--all-sources', action='store_true', help='Scan all databases across both sources')
    parser.add_argument('--summary', action='store_true', help='Combine existing cypher_flags.json into summary')
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
            print(f"CYPHER CORRECTNESS SCAN SUMMARY")
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
        output_path = REPO_ROOT / 'dataset' / source / database / 'cypher_flags.json'
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
        print(f"CYPHER CORRECTNESS SCAN RESULTS")
        print(f"{'='*60}")

        total_queries = sum(r.get('total_queries', 0) for r in all_results)
        total_flagged = sum(r.get('flagged', 0) for r in all_results)
        print(f"Total queries scanned: {total_queries}")
        if total_queries:
            print(f"Total flagged: {total_flagged} ({total_flagged/total_queries*100:.1f}%)")
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
