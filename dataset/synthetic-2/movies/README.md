# Movies Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 738**

Movies, people, genres, reviews.

## Current Status
- `queries.csv`: 737 converted queries
- 1 failed query

Total: 737 + 1 = 738 / 738 ✓

## Failed Queries

### Query 580
**Error:** Unsupported: Cypher `substring()` for dynamic first-character comparison between two variables has no TypeQL equivalent. TypeQL lacks substring/left string extraction functions.
```cypher
WHERE substring(p1.name, 0, 1) = substring(p2.name, 0, 1)
```
