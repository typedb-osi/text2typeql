# Network Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 625**

Data centers, machines, software, network topology.

## Current Status
- `queries.csv`: 620 converted queries
- 5 failed queries

Total: 620 + 5 = 625 / 625 ✓

## Schema Notes
- `Zone` (Neo4j label) renamed to `network_zone` (reserved keyword in TypeQL)
- `Type` (Neo4j label) renamed to `machine_type_spec` (reserved keyword in TypeQL)

## Failed Queries (5 total)

### Query 347
**Reason:** Requires `COLLECT(DISTINCT ...)` to aggregate machine types into a list. TypeQL has no `collect()` function.
```cypher
MATCH (rack:Rack {name: 'DC1-RCK-4-9'})-[:HOLDS]->(machine:Machine)-[:TYPE]->(type:Type)
RETURN COUNT(machine) AS machine_count, COLLECT(DISTINCT type.type) AS machine_types
```

### Query 382
**Reason:** Requires `collect()` to aggregate machine names into a list. TypeQL has no `collect()` function.
```cypher
MATCH (rack:Rack {rack: 3})-[:HOLDS]->(machine:Machine)
RETURN count(machine) AS machine_count, collect(machine.name) AS machine_names
```

### Query 525
**Reason:** Requires `COLLECT()` with map construction and array slicing (`[0..3]`) for per-zone top-3 ranking. TypeQL has no collect, map literals, or array slicing.
```cypher
MATCH (r:Rack)-[:HOLDS]->(m:Machine)
WITH r.zone AS zone, r.name AS rackName, COUNT(m) AS machineCount
ORDER BY zone, machineCount DESC
WITH zone, COLLECT({rackName: rackName, machineCount: machineCount}) AS racksByZone
RETURN zone, racksByZone[0..3] AS top3RacksByZone
```

### Query 527
**Reason:** Requires `collect()` to aggregate dependency names. Additionally, `version` entity cannot play the `depends_on:dependent` role per the TypeQL schema, so the OPTIONAL MATCH dependency pattern is not expressible.
```cypher
MATCH (v:Version {name: '7.1'})<-[:PREVIOUS]-(prev:Version)
OPTIONAL MATCH (prev)-[:DEPENDS_ON]->(dep:Version)
RETURN prev.name AS PreviousVersion, collect(dep.name) AS Dependencies
```

### Query 623
**Reason:** Schema mismatch — `interface` entity does not have a `name` attribute in the TypeQL schema. Cypher references `interface.name` which does not exist.
```cypher
MATCH (network:Network {ip: '10.2'})-[:ROUTES]->(interface:Interface)
RETURN interface.ip AS ip, interface.name AS name
```

## Resolved Queries

### Queries 1, 201, 228, 259, 603 (resolved)
Previously failed due to variable-length path traversal (`[:PREVIOUS*]`, `[:PREVIOUS*1..N]`). Converted using recursive stream functions that traverse the `previous` relation transitively. TypeDB tables recursive functions to avoid cycles and returns results breadth-first.

### Query 397 (resolved)
Previously failed due to `[:DEPENDS_ON*]` transitive closure. Converted using recursive stream function with `$dep is $sw` identity base case to include direct dependencies in results.

### Query 560 (resolved)
Previously failed due to `[:PREVIOUS*1..3]` + `collect()`. The VLP was handled by recursive stream function; `collect()` was replaced with flat rows (version + optional software name).
