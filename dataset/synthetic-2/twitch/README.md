# Twitch Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 576**

Streams, users, games, teams, follows.

## Current Status
- `queries.csv`: 572 converted queries
- 4 failed queries

Total: 572 + 4 = 576 / 576 ✓

## Failed Queries

### Query 92
**Reason:** String indexing — Cypher uses `g.name[0]` to extract the first character of a string. TypeQL has no substring or character extraction functions.

```cypher
MATCH (s:Stream)-[:HAS_LANGUAGE]->(l:Language), (s)-[:PLAYS]->(g:Game)
WHERE l.name STARTS WITH g.name[0]
RETURN s.name AS stream_name, l.name AS language_name, g.name AS game_name
ORDER BY s.createdAt
LIMIT 5
```

### Query 131
**Reason:** Schema hallucination + date arithmetic — Cypher references `r.since` property on VIP relationship which does not exist in the schema. Also uses `duration.inSeconds().years` which has no TypeQL equivalent.

```cypher
MATCH (u:User)-[r:VIP]->(s:Stream)
WHERE duration.inSeconds(r.since, datetime()).years > 3
RETURN s.name AS stream_name, r.since AS vip_since
ORDER BY r.since
LIMIT 3
```

### Query 141
**Reason:** Substring comparison — Cypher uses `substring()` and `toLower()` to compare first characters of two strings. TypeQL has no substring function.

```cypher
MATCH (s:Stream)-[:PLAYS]->(g:Game), (s)-[:HAS_TEAM]->(t:Team)
WHERE toLower(substring(g.name, 0, 1)) = toLower(substring(t.name, 0, 1))
RETURN s.name AS stream_name, g.name AS game_name, t.name AS team_name
ORDER BY s.createdAt
LIMIT 3
```

### Query 419
**Reason:** Word counting — Cypher uses `split()` and `size()` to count words in a string. TypeQL has no split or word-counting functions.

```cypher
MATCH (s:Stream)-[:CHATTER]->(u:User)
WHERE size(split(s.description, " ")) > 50
RETURN s
ORDER BY s.createdAt ASC
LIMIT 3
```

## Resolved Queries

### Query 360 (resolved)
Previously failed due to variable-length path `[:MODERATOR*]`. Converted using recursive stream function `all_chain_members()` to transitively follow moderation relations, then count distinct reachable streams.

## Conversion Notes

### Query 120: hardcoded date cutoff
"Most chatters in the past month" — Cypher uses `datetime() - duration('P1M')`. Converted with hardcoded cutoff `>= 2021-04-01T00:00:00` (dataset max stream date is 2021-05-09).
