# FinCEN Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 614**

Financial filings, banks, countries.

## Current Status
- `queries.csv`: 609 converted queries
- 5 failed queries

Total: 609 + 5 = 614 / 614 ✓

## Failed Queries (5 total)

### Query 20
**Reason:** Requires `toFloat()` for string-to-numeric casting and `abs()` on computed differences. TypeQL cannot cast string attributes to numeric types.
```cypher
MATCH (f:Filing)
WITH f,
     toFloat(f.origin_lat) AS origin_lat,
     toFloat(f.beneficiary_lat) AS beneficiary_lat,
     abs(toFloat(f.origin_lat) - toFloat(f.beneficiary_lat)) AS lat_diff
ORDER BY lat_diff DESC
LIMIT 3
RETURN f.sar_id AS filing_id, f.originator_bank AS originator_bank, f.beneficiary_bank AS beneficiary_bank, lat_diff
```

### Query 374
**Reason:** Requires `duration.inMonths()` for exact month-duration comparison. Months have variable days (28-31), so "exactly one month" is not expressible as a fixed duration in TypeQL.
```cypher
MATCH (f:Filing)
WHERE duration.inMonths(datetime(f.begin), datetime(f.end)).months = 1
RETURN f
ORDER BY f.begin
LIMIT 3
```

### Query 405
**Reason:** Requires datetime component extraction (`date().month`) to filter by Q4 (months 10-12) across arbitrary years. TypeQL has no function to extract month components from datetime values.
```cypher
MATCH (f:Filing)-[:ORIGINATOR]->(e:Entity)-[:COUNTRY]->(c:Country)
WHERE (f.begin >= datetime({year: 2000, month: 10, day: 1}) AND f.begin <= datetime({year: 2000, month: 12, day: 31}))
   OR (f.begin >= datetime({year: 2001, month: 10, day: 1}) AND f.begin <= datetime({year: 2001, month: 12, day: 31}))
   -- ... repeated for years 2000-2017
RETURN c.name AS country, COUNT(f) AS filings
ORDER BY filings DESC
LIMIT 5
```

### Query 434
**Reason:** Same as Query 20 — requires `toFloat()` for string-to-numeric casting and `abs()` on computed latitude differences. Schema stores lat/lon as strings.
```cypher
MATCH (f:Filing)
WITH f,
     toFloat(f.origin_lat) AS origin_lat,
     toFloat(f.beneficiary_lat) AS beneficiary_lat,
     abs(toFloat(f.origin_lat) - toFloat(f.beneficiary_lat)) AS lat_diff
ORDER BY lat_diff DESC
LIMIT 3
RETURN f.sar_id AS filing_id, lat_diff
```

### Query 550
**Reason:** Requires `substring()` to extract and compare month portions of two string attributes. TypeQL has no substring or string slicing functions.
```cypher
MATCH (f:Filing)
WHERE f.begin_date_format STARTS WITH '2015' AND f.end_date_format STARTS WITH '2015'
  AND substring(f.begin_date_format, 5, 2) = substring(f.end_date_format, 5, 2)
RETURN f
```

## Conversion Notes

### Queries converted with TypeDB 3.8 datetime arithmetic (25 queries)

Queries 6, 23, 48, 52, 75, 87, 116, 145, 149, 167, 187, 205, 222, 226, 242, 319, 354, 427, 477, 508, 542, 566, 577, 611, 612 used Cypher `duration.between()` / `duration.inSeconds()` / `duration.inDays()` to compute filing duration. Converted using TypeDB 3.8 datetime subtraction: `let $diff = $period_end - $period_begin;` with `sort $diff` for ordering by duration.

