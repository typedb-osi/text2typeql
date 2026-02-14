# GRANDstack Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 807**

Businesses, reviews, users, categories.

## Current Status
- `queries.csv`: 805 converted queries
- 2 failed queries

Total: 805 + 2 = 807 / 807 ✓

## Failed Queries (2 total)

Both failures involve Neo4j's spatial `POINT` type with sub-property access (`.latitude`). TypeQL does not yet support structured/composite value types. This will be unblocked when **structs** are implemented in TypeQL, allowing typed composite attributes with named fields.

### Query 356
**Reason:** Neo4j Point type — `location.latitude` sub-property access not supported in TypeQL. Requires struct types to model Point with latitude/longitude fields.
```cypher
MATCH (b:Business)
WHERE b.location.latitude > 46.87
RETURN b.name
```

### Query 460
**Reason:** Neo4j Point type — `location.latitude` sub-property access not supported in TypeQL. Requires struct types to model Point with latitude/longitude fields.
```cypher
MATCH (b:Business)
WHERE b.location.latitude > 37
RETURN b.name AS businessName, b.location AS location
```

## Resolved Queries

### Queries 26, 36, 179, 219, 229 (resolved)
Previously failed due to `collect()` + computation (`size()`, `WHERE =`, array slicing). Converted using custom functions: `category_count()` for distinct count, `avg_stars()` for mean aggregation, `reviewed_by()` for per-user existence checks, `latest_review_date()` for chained reduce, and `distinct_date_count()` for date filtering.

### Queries 202, 513, 766 (resolved)
Previously failed due to `collect()` for display grouping. Converted as flat rows — each (entity, detail) pair is a separate result row instead of a grouped list.

### Queries 174, 238, 693, 745 (resolved)
Previously failed due to `size()` string length. Converted using `len()` (TypeDB 3.8+).
