# Twitch Dataset

**Source:** `synthetic_opus_demodbs` (Neo4j text2cypher)

**Total queries in original dataset: 561**

## Current Status
- `queries.csv`: 554 successfully converted and validated queries
- 7 queries that cannot be converted (documented below in Failed Queries)

Total: 554 + 7 = 561 ✓

## Failed Queries (7 total)

### Query 26
**Reason:** Cypher schema error — `PLAYS` goes Stream→Game, not User→Stream. Query asks for streams played by users which is an incorrect relationship direction.
```cypher
MATCH (s:Stream)<-[:PLAYS]-(u:User)
WITH s, count(distinct u) as userCount
WHERE userCount > 5
RETURN s.name as streamName, s.url as streamUrl, userCount
ORDER BY userCount DESC
LIMIT 5
```

### Query 180
**Reason:** User entity has no `description` attribute, and TypeQL lacks `split()` for word counting.
```cypher
MATCH (s:Stream)<-[:CHATTER]-(u:User)
WHERE size(split(u.description, ' ')) > 50
RETURN s.name, s.url
LIMIT 3
```

### Query 227
**Reason:** Cypher schema error — `PLAYS` goes Stream→Game, not User→Stream.
```cypher
MATCH (s:Stream)<-[:PLAYS]-(u:User)
WHERE u.name CONTAINS 'doduik' AND s.total_view_count > 3000
RETURN s
```

### Query 282
**Reason:** No `left()` string function — cannot extract and compare first characters of language and game names.
```cypher
MATCH (s:Stream)-[:HAS_LANGUAGE]->(l:Language), (s)-[:PLAYS]->(g:Game)
WHERE left(l.name, 1) = left(g.name, 1)
RETURN s.name AS stream, l.name AS language, g.name AS game
LIMIT 5
```

### Query 286
**Reason:** Datetime arithmetic (`datetime() - duration('P1M')`) not available in TypeQL.
```cypher
MATCH (s:Stream)<-[:CHATTER]-(chatter)
WHERE s.createdAt >= datetime() - duration('P1M')
WITH s, count(chatter) AS chatterCount
RETURN s.name AS streamName, chatterCount
ORDER BY chatterCount DESC
LIMIT 3
```

### Query 304
**Reason:** No `left()` string function — cannot extract and compare first characters of game and team names.
```cypher
MATCH (s:Stream)-[:PLAYS]->(g:Game), (s)-[:HAS_TEAM]->(t:Team)
WHERE left(g.name, 1) = left(t.name, 1)
RETURN s.name AS stream, g.name AS game, t.name AS team
LIMIT 3
```

### Query 316
**Reason:** No timestamp on VIP relation for duration calculation, and TypeQL lacks `duration.between()`.
```cypher
MATCH (s:Stream)-[r:VIP]->(u:User)
WHERE duration.between(r.createdAt, date()).years >= 3
WITH s, u
ORDER BY r.createdAt
LIMIT 3
RETURN s.name AS stream, u.name AS user
```

## Original Cypher Errors

During conversion, TypeDB's strict schema enforcement caught cases where the original Cypher query referenced relationships or attributes that do not exist in the schema, or used them in the wrong direction.

### Wrong PLAYS direction (3 queries)

The Cypher assumes `(User)-[:PLAYS]->(Game)` or `(User)-[:PLAYS]->(Stream)`, but in the schema PLAYS goes from Stream to Game (`(Stream)-[:PLAYS]->(Game)`). Users do not play games — streams do.

| Index | Question | Cypher error |
|-------|----------|-------------|
| 26 | "First 5 streams played by more than 5 users" | `(s:Stream)<-[:PLAYS]-(u:User)` — PLAYS goes Stream→Game, not User→Stream |
| 227 | "Streams played by users with name containing 'doduik'" | `(s:Stream)<-[:PLAYS]-(u:User)` — same incorrect direction |
| 533 | "Streams with same game played by itsbigchase and 9linda" | `(u1:User)-[:PLAYS]->(g:Game)` — users don't play games, streams do |

**How TypeDB caught it:** The `game_play` relation has explicit roles `streaming_channel` (Stream) and `played_game` (Game). A User entity cannot fill the `streaming_channel` role — the type system rejects it. The TypeQL for query 533 correctly uses stream entities: `game_play (streaming_channel: $s1, played_game: $g)`.

### Wrong entity type constraints (2 queries)

| Index | Question | Cypher error |
|-------|----------|-------------|
| 526 | "Streams that are VIPs in stream 'itsbigchase'" | `(s:Stream)-[:VIP]->(stream:Stream)` — VIP requires a User, not a Stream |
| 207 | "Streams with chatters who are also streams" | `WHERE exists{ (chatter:Stream) }` — checks if a User is also a Stream |

**How TypeDB caught it:** TypeQL role constraints enforce that only `user` entities can fill `vip_user` and only `stream` entities can fill `channel_with_vips`. Query 526 was convertible by using the `vip_channel` role for streams (channels where a stream is a VIP). Query 207 was convertible via `chat_activity` using `chatting_channel` role (streams that chat in other streams).
