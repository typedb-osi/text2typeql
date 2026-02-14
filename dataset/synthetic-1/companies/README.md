# Companies Dataset

**Source:** `synthetic_opus_demodbs` (Neo4j text2cypher)

**Total queries in original dataset: 933**

## Current Status
- `queries.csv`: 930 successfully converted and validated queries
- 3 queries that cannot be converted (documented below in Failed Queries)

Total: 930 + 3 = 933 ✓

## Schema Notes
- The `mentions` relation uses a generic `mentioned` role (not `organization`) so both organizations and cities can be mentioned in articles.

## Failed Queries (3 total)

### Query 341
**Reason:** TypeQL lacks `left()` string manipulation and `date().year` — cannot extract birth year from `person_id` to compute age.
```cypher
MATCH (o:Organization)-[:HAS_CEO]->(ceo:Person)
WHERE date().year - toInteger(left(ceo.id, 4)) < 40
RETURN o.name
```

### Query 783
**Reason:** Semantically invalid — Accenture is an organization, not a person, so it cannot be a CEO. TypeDB's type system enforces that the `ceo` role requires a `person` entity.
```cypher
MATCH (o:Organization)-[:HAS_CEO]->(p:Person {name: 'Julie Spellman Sweet'})
WHERE p.summary IS NOT NULL AND p.summary CONTAINS 'Accenture'
RETURN o.name
```

### Query 843
**Reason:** TypeQL lacks relative date support — requires `now()` for `datetime() - duration()` calculation.
```cypher
MATCH (o:Organization)-[:HAS_CEO]->(ceo:Person)
WHERE o.isDissolved = true
  AND EXISTS {
    (o)<-[:MENTIONS]-(a:Article)
    WHERE a.date >= datetime() - duration('P1Y')
  }
RETURN ceo.name AS ceoName, o.name AS orgName
```

## Original Cypher Errors

During conversion, TypeDB's explicit role system and semantic review caught cases where the original Cypher was incorrect or ambiguous.

### Reversed supplier/customer direction (5 queries)

Neo4j's `HAS_SUPPLIER` relationship is ambiguous: `(A)-[:HAS_SUPPLIER]->(B)` means B is a supplier to A, but the variable naming and traversal direction in several queries reverses the semantics. TypeQL's `supplies (supplier: $x, customer: $y)` makes the direction unambiguous.

| Index | Question | Cypher error |
|-------|----------|-------------|
| 488 | "Organizations that are suppliers to New Energy Group" | Cypher direction returns NEG's customers, not its suppliers |
| 526 | "Which organizations does New Energy Group supply?" | Cypher gets NEG's suppliers, not organizations NEG supplies to |
| 600 | "3 organizations that are suppliers to New Energy Group" | Same reversed direction |
| 647 | "Organizations that are suppliers to public companies" | Variable naming swaps supplier/customer, filter applies to wrong entity |
| 733 | "Top 3 suppliers of New Energy Group" | Same reversed direction |

**How TypeDB caught it:** The `supplies` relation has explicit `supplier` and `customer` roles. Writing `supplies (supplier: $s, customer: $o)` forces the converter to decide which entity fills which role, making direction errors immediately visible during semantic review.

### Semantically invalid questions (2 queries)

| Index | Question | Cypher error |
|-------|----------|-------------|
| 591 | "Organizations mentioned in articles authored by women" | Cypher filters for `{author: 'David Correa'}` — a man's name. The question and Cypher contradict. |
| 783 | "Organizations that have Accenture as their CEO" | Accenture is an organization, not a person. CEOs must be persons. Semantically invalid (in `failed.csv`). |

**How TypeDB caught it:** Query 783 is caught by type constraints — the `ceo` role in the `ceo_of` relation requires a `person` entity, not an `organization`. Query 591 was caught during semantic review when verifying the TypeQL against the English question.
