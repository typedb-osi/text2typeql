#!/usr/bin/env python3
"""Parse TypeQL schema files into structured data for type checking.

Returns a dict with:
  - attributes: {name: value_type}
  - entities: {name: {owns: [attr_names], plays: [(relation, role)]}}
  - relations: {name: {relates: {role: None}, owns: [attr_names]}}
  - subtypes: {child: parent}
  - role_players: {(relation, role): [entity_names]}
"""

import re
import sys
from pathlib import Path

# TypeQL identifiers can contain hyphens (e.g., location-contains, start-date)
ID = r'[\w][\w-]*'


def parse_schema(schema_path: str) -> dict:
    """Parse a TypeQL schema file into structured type inventory."""
    text = Path(schema_path).read_text()

    attributes = {}
    entities = {}
    relations = {}
    subtypes = {}

    # Remove comments
    text = re.sub(r'#[^\n]*', '', text)

    # Remove 'define' keyword
    text = re.sub(r'^\s*define\s*', '', text, flags=re.MULTILINE)

    # Strategy: find each top-level keyword and collect until the next one
    decl_pattern = re.compile(
        rf'(attribute|entity|relation)\s+({ID})(.*?)(?=(?:attribute|entity|relation)\s+{ID}|$)',
        re.DOTALL
    )

    for match in decl_pattern.finditer(text):
        kind = match.group(1)
        name = match.group(2)
        body = match.group(3).strip()

        if kind == 'attribute':
            vtype_match = re.search(r'value\s+(\w+)', body)
            value_type = vtype_match.group(1) if vtype_match else 'string'
            attributes[name] = value_type

        elif kind == 'entity':
            entity_info = {'owns': [], 'plays': []}

            # Check for subtype
            sub_match = re.search(rf'sub\s+({ID})', body)
            if sub_match:
                parent = sub_match.group(1)
                subtypes[name] = parent

            # Parse owns (attribute names can have hyphens)
            for owns_match in re.finditer(rf'owns\s+({ID})', body):
                entity_info['owns'].append(owns_match.group(1))

            # Parse plays: relation:role (both can have hyphens)
            for plays_match in re.finditer(rf'plays\s+({ID}):({ID})', body):
                rel = plays_match.group(1)
                role = plays_match.group(2)
                entity_info['plays'].append((rel, role))

            entities[name] = entity_info

        elif kind == 'relation':
            rel_info = {'relates': {}, 'owns': []}

            # Check for subtype
            sub_match = re.search(rf'sub\s+({ID})', body)
            if sub_match:
                parent = sub_match.group(1)
                subtypes[name] = parent

            # Parse relates
            for relates_match in re.finditer(rf'relates\s+({ID})', body):
                role = relates_match.group(1)
                rel_info['relates'][role] = None

            # Parse owns
            for owns_match in re.finditer(rf'owns\s+({ID})', body):
                rel_info['owns'].append(owns_match.group(1))

            relations[name] = rel_info

    # Build role_players: which entity types can play which (relation, role)
    role_players = {}
    for entity_name, info in entities.items():
        for rel, role in info['plays']:
            key = (rel, role)
            if key not in role_players:
                role_players[key] = []
            role_players[key].append(entity_name)

    # Propagate inherited owns/plays from parent to child
    for child, parent in subtypes.items():
        if child in entities and parent in entities:
            parent_info = entities[parent]
            child_info = entities[child]
            # Inherit owns not already declared
            for attr in parent_info['owns']:
                if attr not in child_info['owns']:
                    child_info['owns'].append(attr)
            # Inherit plays not already declared
            for play in parent_info['plays']:
                if play not in child_info['plays']:
                    child_info['plays'].append(play)
                    # Also add to role_players
                    if play not in role_players:
                        role_players[play] = []
                    if child not in role_players[play]:
                        role_players[play].append(child)

    # All valid type names (entities + relations)
    all_types = set(entities.keys()) | set(relations.keys())

    # All valid attribute names
    all_attributes = set(attributes.keys())

    # All valid role names per relation
    all_roles = {}
    for rel_name, rel_info in relations.items():
        all_roles[rel_name] = set(rel_info['relates'].keys())

    # Relation-owned attributes
    relation_attrs = {}
    for rel_name, rel_info in relations.items():
        if rel_info['owns']:
            relation_attrs[rel_name] = set(rel_info['owns'])

    return {
        'attributes': attributes,
        'entities': entities,
        'relations': relations,
        'subtypes': subtypes,
        'role_players': {f"{k[0]}:{k[1]}": v for k, v in role_players.items()},
        'all_types': all_types,
        'all_attributes': all_attributes,
        'all_roles': all_roles,
        'relation_attrs': relation_attrs,
    }


def main():
    """CLI: parse_schema.py <schema.tql> [--json]"""
    import json

    if len(sys.argv) < 2:
        print("Usage: parse_schema.py <schema.tql> [--json]", file=sys.stderr)
        sys.exit(1)

    schema = parse_schema(sys.argv[1])

    if '--json' in sys.argv:
        # Convert sets to lists for JSON serialization
        serializable = {
            'attributes': schema['attributes'],
            'entities': schema['entities'],
            'relations': schema['relations'],
            'subtypes': schema['subtypes'],
            'all_types': sorted(schema['all_types']),
            'all_attributes': sorted(schema['all_attributes']),
            'all_roles': {k: sorted(v) for k, v in schema['all_roles'].items()},
            'relation_attrs': {k: sorted(v) for k, v in schema['relation_attrs'].items()},
            'role_players': schema['role_players'],
        }
        print(json.dumps(serializable, indent=2))
    else:
        print(f"Entities: {sorted(schema['entities'].keys())}")
        print(f"Relations: {sorted(schema['relations'].keys())}")
        print(f"Attributes: {sorted(schema['all_attributes'])}")
        for ent, info in sorted(schema['entities'].items()):
            print(f"  {ent}: owns {info['owns']}")
        for rel, info in sorted(schema['relations'].items()):
            roles = list(info['relates'].keys())
            owns = info['owns']
            print(f"  {rel}: roles {roles}" + (f", owns {owns}" if owns else ""))


if __name__ == '__main__':
    main()
