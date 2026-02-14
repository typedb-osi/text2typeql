# Offshore Leaks Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 507**

Entities, officers, intermediaries, addresses.

## Current Status
- `queries.csv`: 498 converted queries
- 9 failed queries

Total: 498 + 9 = 507 / 507 ✓

## Failed Queries

### Query 41
**Reason:** Schema mismatch — Cypher uses `similar` relation between Entity and Other, but in TypeQL schema the `other` entity does not play similar relation roles (only intermediary and officer can participate).

```cypher
MATCH (e:Entity)-[:similar]->(o:Other)
WHERE o.name = 'Top Games Holdings Inc.'
RETURN e.name AS EntityName, e.address AS EntityAddress
```

### Query 61
**Reason:** Schema mismatch — the `other` entity type does not play any role in the `similar` relation. Only intermediary and officer can participate.

```cypher
MATCH (e:Entity)-[:similar]->(o:Other)
WHERE o.name = 'NINGBO SUNRISE ENTERPRISES UNITED CO., LTD.'
RETURN e.name AS entity_name, e.address AS entity_address
```

### Query 111
**Reason:** Date month extraction — Cypher uses `STARTS WITH 'MAR'` on date field. TypeQL date type does not support string pattern matching or month extraction functions.

```cypher
MATCH (e:Entity)
WHERE e.jurisdiction_description = 'Samoa' AND e.incorporation_date STARTS WITH 'MAR'
RETURN e.name, e.incorporation_date
```

### Query 146
**Reason:** Date component extraction — Cypher uses `SPLIT()` and array indexing to extract year from date strings. TypeQL has no `SPLIT()`, array indexing, or `year()` function.

```cypher
MATCH (e:Entity)
WHERE e.incorporation_date IS NOT NULL AND e.struck_off_date IS NOT NULL
WITH e,
     toInteger(SPLIT(e.incorporation_date, "-")[2]) AS incorporation_year,
     toInteger(SPLIT(e.struck_off_date, "-")[2]) AS struck_off_year
WHERE incorporation_year = struck_off_year
RETURN e.name AS entity_name, e.incorporation_date, e.struck_off_date
```

### Query 168
**Reason:** Schema mismatch — `offshore_entity` does not play any role in the `similar` relation, and `other` entity does not have `address` attribute. The `similar` relation only connects intermediary and officer entities.

```cypher
MATCH (e:Entity)-[:similar]->(o:Other)
WHERE e.name = 'HOTFOCUS CO., LTD.'
RETURN o.name AS similar_name, o.address AS similar_address
```

### Query 372
**Reason:** Date component extraction — requires `substring()` to extract year from date. TypeQL has no date component extraction or string substring functions.

```cypher
MATCH (e:Entity)
WHERE e.struck_off_date IS NOT NULL AND e.inactivation_date IS NOT NULL
AND substring(e.struck_off_date, -4) = substring(e.inactivation_date, -4)
RETURN e.name AS entity_name, e.struck_off_date, e.inactivation_date
```

### Query 399
**Reason:** Date component extraction — `substring()` for year comparison not supported in TypeQL.

```cypher
MATCH (e:Entity)
WHERE e.incorporation_date IS NOT NULL AND e.struck_off_date IS NOT NULL
AND substring(e.incorporation_date, -4) = substring(e.struck_off_date, -4)
RETURN e.name AS entity_name, e.incorporation_date, e.struck_off_date
```

### Query 437
**Reason:** Dynamic string contains — Cypher uses `CONTAINS` between two variables. TypeQL's `like` operator requires a literal pattern string, not a variable reference.

```cypher
MATCH (i:Intermediary)-[:registered_address]->(a:Address)
WHERE NOT i.countries CONTAINS a.countries
RETURN i.name AS IntermediaryName, i.countries AS IntermediaryCountry, a.address AS RegisteredAddress, a.countries AS AddressCountry
```

### Query 472
**Reason:** Schema mismatch — same as queries 41/61. `offshore_entity` and `other` do not play `similar` roles; only intermediary and officer can participate.

```cypher
MATCH (e:Entity)-[:similar]->(o:Other)
WHERE o.name = 'NINGBO SUNRISE ENTERPRISES UNITED CO., LTD.'
RETURN e.name AS EntityName, e.address AS EntityAddress
```

## Resolved Queries

### Query 103 (resolved)
Previously failed due to schema mismatch (officer vs intermediary types). Reinterpreted from English: intermediaries connected to >1 offshore entity, using `entity_count()` custom function.

### Query 370 (resolved)
Previously failed due to `collect()` + `size()`. Converted using `address_count()` function counting distinct postal_address entities per offshore_entity via `registered_address` relation.

### Query 476 (resolved)
Previously failed due to `split()` + `size()` on semicolon-delimited string. Reinterpreted using TypeQL multi-cardinality: count distinct `former_name` attributes > 1.

### Query 324 (resolved)
Previously failed due to officer entity missing `status` attribute. Added `owns status` to officer entity in schema, then converted using simple attribute filter.

### Query 491 (resolved)
Previously failed due to `STARTS WITH 'FEB-2013'` string pattern matching on dates. Converted using date range comparison: `$d >= 2013-02-01; $d < 2013-03-01;`.

