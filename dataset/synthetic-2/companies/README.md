# Companies Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 966**

Companies, people, investments, locations.

## Current Status
- `queries.csv`: 966 converted queries
- 0 failed queries

Total: 966 + 0 = 966 / 966 ✓

## Failed Queries

None.

### Query 662 (resolved)
Previously failed due to variable-length path `[:HAS_SUPPLIER*]`. Converted using recursive stream functions to traverse the supply chain transitively and count distinct supplier nodes.

## Conversion Notes

### Queries converted from s1 equivalent (14 queries)

14 queries that were originally marked as failed had exact matches in synthetic-1/companies that were successfully converted. The s1 TypeQL was reused since both datasets share the identical schema. Many of these had Cypher that referenced non-existent Neo4j schema elements (capital city properties, gender, nationality), but s1 found valid TypeQL reinterpretations.

### Queries converted with approximations

Several queries used Cypher `WITH...ORDER BY...LIMIT` subquery patterns (get N entities first, then expand). These were converted to flat TypeQL joins with a single `sort`/`limit` at the end, which limits result rows rather than the intermediate entity set.

| Index | Pattern | Approximation |
|-------|---------|---------------|
| 85 | Board members of first 3 Technology orgs | Flat join, limit 3 rows |
| 372 | Board members of first 3 public orgs | Flat join, limit 3 rows |
| 890 | Top 3 orgs with CEO in latest articles | Sort by article date, limit 3 rows |
| 905 | First 3 investors in Accenture + other investments | Flat join, all results |

### Queries converted with hardcoded dates

Queries 637 and 723 ask about CEO tenure "over a decade". The Cypher references `Person.startDate` (which doesn't exist in Neo4j), but the TypeQL schema correctly models `start-date` as an attribute of the `ceo_of` relation. The date threshold was hardcoded to `2012-01-01` based on the dataset creation date (~2022).

### Query 593: hardcoded date cutoff
"Organizations that changed CEO in the past year" — Cypher uses `datetime().year - 1`. Converted with hardcoded cutoff `start-date >= 2021-01-01T00:00:00` on the `ceo_of` relation.

### Query 18: reinterpreted MENTIONS target

"CEO with a name mentioned in at least two different articles" — Cypher uses `Article-[:MENTIONS]->Person` but MENTIONS only targets Organization. Reinterpreted as organization (with CEO) mentioned in 2+ articles, matching s1 query 929 which has the identical question.

### Query 598: collect() dropped

"Which organizations have a CEO who is also an investor in other organizations?" — Cypher uses `collect()` for display grouping. TypeQL returns flat (org, ceo, investedOrg) rows instead.
