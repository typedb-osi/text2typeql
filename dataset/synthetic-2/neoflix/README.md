# NeoFlix Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 923**

Movies, ratings, genres, subscriptions.

## Current Status
- `queries.csv`: 916 converted queries
- 7 failed queries

Total: 916 + 7 = 923 / 923 ✓

## Failed Queries (7 total)

### Query 40
**Reason:** Requires `split()` and `size()` for word counting. TypeQL has no string splitting or array size functions.
```cypher
MATCH (m:Movie)
WITH m, size(split(m.overview, " ")) AS word_count
ORDER BY word_count DESC
LIMIT 5
RETURN m.title AS MovieTitle, word_count AS OverviewWordCount
```

### Query 156
**Reason:** Requires `split()` and `size()` for word counting. Same limitation as Query 40.
```cypher
MATCH (m:Movie)
RETURN m.title, m.overview, size(split(m.overview, " ")) AS word_count
ORDER BY word_count DESC
LIMIT 3
```

### Query 171
**Reason:** Requires date component extraction (`release_date.year`) and modulo arithmetic (`%`) for leap year calculation. TypeQL has neither.
```cypher
MATCH (a:Adult)
WHERE (a.release_date.year % 4 = 0 AND a.release_date.year % 100 <> 0) OR (a.release_date.year % 400 = 0)
RETURN a.title, a.release_date
ORDER BY a.release_date DESC
LIMIT 3
```

### Query 573
**Reason:** Requires date arithmetic (`latest_date - earliest_date`) combined with `collect()` / `UNWIND` for per-collection date range computation. TypeQL has no collect/unwind functions.
```cypher
MATCH (m:Movie)-[:IN_COLLECTION]->(c:Collection)
WITH c, collect(m) AS movies
UNWIND movies AS movie
WITH c, movie, min(movie.release_date) AS earliest_date, max(movie.release_date) AS latest_date
WITH c, latest_date - earliest_date AS date_range
ORDER BY date_range DESC
LIMIT 5
MATCH (m:Movie)-[:IN_COLLECTION]->(c)
RETURN c.name AS collection_name, m.title AS movie_title, m.release_date AS release_date
ORDER BY collection_name, release_date
```

### Query 581
**Reason:** Requires date component extraction (`release_date.year`) and modulo arithmetic (`%`) for leap year calculation. Same limitation as Query 171.
```cypher
MATCH (m:Movie)
WHERE (m.release_date.year % 4 = 0 AND m.release_date.year % 100 <> 0) OR (m.release_date.year % 400 = 0)
RETURN m.title, m.release_date
```

### Query 752
**Reason:** Requires `split()` and `size()` for word counting in taglines. Same limitation as Query 40.
```cypher
MATCH (m:Movie)
WHERE m.tagline IS NOT NULL
RETURN m.title, m.tagline, size(split(m.tagline, " ")) AS tagline_length
ORDER BY tagline_length DESC
LIMIT 5
```

### Query 829
**Reason:** Requires `apoc.text.levenshteinDistance()` for string edit distance computation. TypeQL has no string distance or similarity functions.
```cypher
MATCH (m:Movie)
WITH m,
     apoc.text.levenshteinDistance(m.original_title, m.title) AS title_difference
ORDER BY title_difference ASC
LIMIT 3
RETURN m.title AS final_title, m.original_title AS original_title, title_difference
```

## Conversion Notes

### Query 621: hardcoded date cutoff
"Movies with highest popularity released in the last 5 years" — Cypher uses `date().year - 5`. Converted with hardcoded cutoff `release_date >= 2017-01-01` (dataset is from ~2022).
