# Stack Overflow 2 Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 307**

Questions, answers, comments, tags, users.

## Current Status
- `queries.csv`: 306 converted queries
- 1 failed query

Total: 306 + 1 = 307 / 307 ✓

## Schema Changes

- Added `plays commented_on:question` to `answer` entity, enabling comments on answers (query 91, 261)

## Failed Queries

### Query 94
**Reason:** Epoch timestamp conversion — Cypher uses `date(datetime({epochSeconds: ...}))` to extract dates from epoch integers. TypeQL has no epoch-to-date conversion.

```cypher
MATCH (q:Question)<-[:ANSWERED]-(a:Answer)
WHERE date(datetime({epochSeconds: q.creation_date})) = date(datetime({epochSeconds: a.creation_date}))
WITH q, COUNT(a) AS answer_count
ORDER BY answer_count DESC
LIMIT 3
RETURN q.title AS question_title, q.link AS question_link, q.creation_date AS creation_date, answer_count
```

### Query 169
**Reason:** Current timestamp — Cypher uses `timestamp()` to get the current time. TypeQL has no built-in function for the current timestamp.

```cypher
WITH timestamp() AS current_time, timestamp() - 31536000 AS one_year_ago
MATCH (u:User)-[:ASKED]->(q:Question)
WHERE q.creation_date >= one_year_ago
WITH u, COUNT(q) AS question_count
ORDER BY question_count DESC
LIMIT 10
RETURN u.display_name AS user, question_count
```

## Resolved Queries

### Query 91 (resolved)
Previously failed due to schema mismatch (commented_on only connected comments to questions). Added `plays commented_on:question` to answer entity, then counted comments per answer.

### Query 98 (resolved)
Previously failed due to `size()` function. Converted using `len()` (TypeDB 3.8+).

### Query 253 (resolved)
Previously failed due to `collect()`. Converted using fetch subquery to collect tags as nested array.

### Query 259 (resolved)
Previously failed due to `COLLECT()`. Converted using fetch subquery to collect tags as nested array.

### Query 260 (resolved)
Previously failed due to `collect()`. Converted using fetch subquery to collect tags as nested array.

### Query 261 (resolved)
Previously failed due to nested subqueries/CTEs. Converted using custom function `comment_count_on_top_questions()` with chained match-sort-limit-match pipeline.

### Query 169 (resolved)
Previously failed due to `timestamp()` for current time. Converted using `max_creation_date()` custom function as proxy for "now", then integer subtraction of 31536000 (one year in seconds).

### Query 288 (resolved)
Previously failed due to `collect()`. Converted using fetch subquery to collect tags as nested array.
