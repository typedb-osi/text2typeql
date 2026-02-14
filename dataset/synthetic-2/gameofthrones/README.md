# Game of Thrones Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 393**

Characters, houses, battles, allegiances.

## Current Status
- `queries.csv`: 384 converted queries
- 9 failed queries

Total: 384 + 9 = 393 / 393 ✓

## Failed Queries (9 total)

8 of 9 failures involve Neo4j array element access (`array[N]`) on `fastrf_embedding`. TypeQL multi-cardinality attributes have no positional indexing. This will be unblocked when **list/array value types** are implemented in TypeQL, allowing indexed access to ordered attribute collections.

### Query 119
**Reason:** Requires array index access (`fastrf_embedding[0]`). TypeQL has no positional indexing for multi-cardinality attributes.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[0] > 0.5
RETURN c.name, c.fastrf_embedding
LIMIT 3
```

### Query 121
**Reason:** Requires array index access (`fastrf_embedding[9]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[9] < -0.5
RETURN c.name
LIMIT 3
```

### Query 202
**Reason:** Requires array index access (`fastrf_embedding[0]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[0] > 0
RETURN c.name, c.fastrf_embedding
LIMIT 5
```

### Query 227
**Reason:** Requires array index access (`fastrf_embedding[0]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[0] < 0
RETURN c.name, c.fastrf_embedding
LIMIT 5
```

### Query 250
**Reason:** Requires array index access (`fastrf_embedding[0]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[0] < 0
RETURN c.name
```

### Query 314
**Reason:** Requires array index access (`fastrf_embedding[4]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[4] > 0.5
RETURN c.name
```

### Query 326
**Reason:** Requires `percentileCont()` aggregation function. TypeQL has no percentile or statistical threshold functions.
```cypher
MATCH (c:Character)
WITH percentileCont(c.pagerank, 0.9) AS top10PercentThreshold
MATCH (c:Character)
WHERE c.pagerank >= top10PercentThreshold
RETURN c.name, c.pagerank
ORDER BY c.pagerank DESC
```

### Query 374
**Reason:** Requires array index access (`fastrf_embedding[9]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[9] < -0.5
RETURN c.name
```

### Query 389
**Reason:** Requires array index access (`fastrf_embedding[0]`). Same limitation as Query 119.
```cypher
MATCH (c:Character)
WHERE c.fastrf_embedding[0] > 0.5
RETURN c.name
```

