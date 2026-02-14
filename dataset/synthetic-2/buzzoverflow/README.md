# BuzzOverflow Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 592**

Q&A posts, users, tags, answers, comments.

## Current Status
- `queries.csv`: 585 converted queries
- 7 failed queries

Total: 585 + 7 = 592 / 592 ✓

## Failed Queries (7 total)

### Query 60
**Reason:** Requires `split()` and `size()` for word counting. TypeQL has no string splitting or array size functions.
```cypher
MATCH (q:Question)
WITH q, size(split(q.text, ' ')) AS wordCount
ORDER BY wordCount DESC
LIMIT 5
RETURN q.title AS title, q.text AS text, wordCount
```

### Query 110
**Reason:** Requires `size()` on `apoc.text.regexGroups()` to count URL occurrences within a string. TypeQL has no regex group extraction or pattern occurrence counting.
```cypher
MATCH (q:Question)
WHERE q.text CONTAINS "http://" OR q.text CONTAINS "https://"
RETURN q.title, q.link, q.text, size(apoc.text.regexGroups(q.text, 'http[s]?://[^\\s]+')) AS link_count
ORDER BY link_count DESC
LIMIT 5
```

### Query 139
**Reason:** Requires datetime component extraction (`time().hour`). TypeQL has no function to extract hour/time components from datetime values.
```cypher
MATCH (q:Question)
WHERE time(q.createdAt).hour >= 8 AND time(q.createdAt).hour < 10
RETURN q.title, q.createdAt
ORDER BY q.createdAt DESC
LIMIT 5
```

### Query 454
**Reason:** Requires `size()` on `apoc.text.regexGroups()` to count URL occurrences. Same limitation as Query 110.
```cypher
MATCH (q:Question)
WHERE q.text CONTAINS "http://" OR q.text CONTAINS "https://"
RETURN q.title, q.link, q.text, size(apoc.text.regexGroups(q.text, 'http[s]?://[^\\s]+')) AS link_count
ORDER BY link_count DESC
LIMIT 3
```

### Query 526
**Reason:** Requires `split()` and `size()` for word counting. Same limitation as Query 60.
```cypher
MATCH (q:Question)
WITH q, size(split(q.text, ' ')) AS wordCount
ORDER BY wordCount DESC
LIMIT 3
RETURN q.title AS title, q.text AS text, wordCount
```

### Query 574
**Reason:** Requires datetime component extraction (`date().month`, `date().day`). TypeQL has no function to extract month or day components from datetime values.
```cypher
MATCH (q:Question)
WHERE date(q.createdAt).month = 1 AND date(q.createdAt).day = 1
   OR date(q.createdAt).month = 12 AND date(q.createdAt).day = 25
RETURN q.title, q.link, q.createdAt, q.score
ORDER BY q.score DESC
LIMIT 5
```

### Query 579
**Reason:** Requires `size()` on `apoc.text.regexGroups()` to count URL occurrences. Same limitation as Queries 110 and 454.
```cypher
MATCH (q:Question)
WHERE q.text CONTAINS "http://" OR q.text CONTAINS "https://"
RETURN q.title, q.text, q.link, size(apoc.text.regexGroups(q.text, 'http[s]?://[^\\s]+')) AS link_count
ORDER BY link_count DESC
LIMIT 3
```

## Conversion Notes

### Queries converted with TypeDB 3.8 len() (6 queries)
Queries 36, 135, 138, 177, 345, 451 used Cypher `size()` for string length. Converted using TypeDB 3.8 `len()` function.

### Query 34: simplified to tag+answered filter
"Users who asked questions tagged 'graphql' and answered within the same month" — Cypher compares question date to current month (`date().month`). Simplified to find answered graphql-tagged questions sorted by date, since exact month comparison requires `now()`.

