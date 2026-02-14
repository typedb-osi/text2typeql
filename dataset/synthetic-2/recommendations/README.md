# Recommendations Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 775**

Movies, users, ratings, genres.

## Current Status
- `queries.csv`: 764 converted queries
- 11 failed queries

Total: 764 + 11 = 775 / 775 ✓

## Failed Queries (11 total)

### Query 29
**Reason:** Requires `apoc.date.fields().dayOfWeek` for day-of-week extraction. TypeQL has no function to compute day of week from a date.
```cypher
MATCH (m:Movie)
WHERE apoc.date.fields(m.released).dayOfWeek = 5
RETURN m.title, m.released
ORDER BY m.released
LIMIT 5
```

### Query 396
**Reason:** Requires `date().year` to extract year component from a date value for comparison with an integer. TypeQL has no datetime component extraction functions.
```cypher
MATCH (d:Director)-[:DIRECTED]->(m:Movie)
WHERE d.born IS NOT NULL AND m.year = date(d.born).year
RETURN d.name AS DirectorName, m.title AS MovieTitle, d.born AS BirthYear, m.year AS MovieYear
```

### Query 408
**Reason:** Requires `date()` type casting to compare date portions of string and date attributes. TypeQL has no cross-type date comparison or string-to-date casting.
```cypher
MATCH (a:Actor)-[:ACTED_IN]->(m:Movie)
WHERE date(m.released) = date(a.born)
RETURN a.name AS actorName, m.title AS movieTitle, a.born AS birthDate, m.released AS releaseDate
```

### Query 447
**Reason:** Requires `split()` and `size()` for word counting in bio text. TypeQL has no string splitting function.
```cypher
MATCH (d:Director)-[:DIRECTED]->(m:Movie)
WHERE size(split(d.bio, " ")) > 500
RETURN m.title AS MovieTitle, d.name AS DirectorName
ORDER BY m.released
LIMIT 3
```

### Query 455
**Reason:** Requires `duration.inDays()` and `datetime({epochSeconds: ...})` for epoch-to-date conversion and date arithmetic. TypeQL cannot convert integer timestamps to date values.
```cypher
MATCH (u:User)-[r:RATED]->(m:Movie)
WITH m, r, duration.inDays(date(m.released), date(datetime({epochSeconds: r.timestamp}))) AS gap
RETURN m.title AS movieTitle, gap
ORDER BY gap ASC
LIMIT 5
```

### Query 481
**Reason:** Requires `split()` and `size()` for counting quote characters in plot text. TypeQL has no string splitting function.
```cypher
MATCH (m:Movie)
WITH m, size(split(m.plot, '"')) / 2 AS quote_count
RETURN m.title AS movie_title, quote_count
ORDER BY quote_count DESC
LIMIT 5
```

### Query 537
**Reason:** Requires `split()` and `size()` for word counting in plot text. Same limitation as Query 447.
```cypher
MATCH (m:Movie)
WHERE size(split(m.plot, " ")) > 100
RETURN m.title, m.plot
ORDER BY size(split(m.plot, " ")) DESC
LIMIT 5
```

### Query 609
**Reason:** Requires `datetime({epochSeconds: ...})` for epoch-to-date conversion. TypeQL cannot convert integer timestamps to datetime values for comparison.
```cypher
MATCH (u:User)-[r:RATED]->(m:Movie)
WHERE date(datetime({epochSeconds: r.timestamp})) = date(m.released)
RETURN u.name AS userName, m.title AS movieTitle, r.rating AS rating
```

### Query 676
**Reason:** Requires `date().dayOfWeek` for day-of-week extraction. Same limitation as Query 29.
```cypher
MATCH (m:Movie)
WHERE date(m.released).dayOfWeek = 5
RETURN m.title, m.released
ORDER BY m.imdbRating DESC
LIMIT 3
```

### Query 703
**Reason:** Requires `datetime({epochSeconds: ...})` for epoch-to-date conversion. Same limitation as Query 609.
```cypher
MATCH (u:User)-[r:RATED]->(m:Movie)
WHERE date(datetime({epochSeconds: r.timestamp})) = date(m.released)
RETURN u.name AS userName, m.title AS movieTitle, date(datetime({epochSeconds: r.timestamp})) AS ratingDate
ORDER BY ratingDate
LIMIT 3
```

### Query 733
**Reason:** Schema mismatch — `user` entity does not own the `born` attribute in the TypeQL schema (only `person` does). The Cypher query references a property that does not exist on the User type.
```cypher
MATCH (u:User)-[:RATED]->(m:Movie)
WHERE date(u.born) > date('1980-01-01')
RETURN m.title AS MovieTitle, m.year AS ReleaseYear, u.name AS UserName
```

## Conversion Notes

### Query 529: hardcoded date cutoff
"Top 5 movies released in the last 5 years" — Cypher uses `date().year - 5`. Converted with hardcoded cutoff `released >= 2017-01-01` (dataset is from ~2022).
