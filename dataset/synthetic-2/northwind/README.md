# Northwind Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 807**

Products, orders, suppliers, customers, categories.

## Current Status
- `queries.csv`: 807 converted queries
- 0 failed queries

Total: 807 + 0 = 807 / 807 ✓

## Failed Queries

None.

## Resolved Queries

### Schema fix: freight attribute type (24 queries resolved)
Queries 66, 78, 98, 145, 148, 161, 167, 176, 261, 269, 308, 322, 375, 402, 470, 515, 520, 522, 634, 637, 672, 718, 767, 789 all required numeric operations on `freight` (comparison, sort, sum, avg). The original Neo4j dataset stored freight as a string and used `toFloat()` at query time. Fixed by changing the schema from `attribute freight value string` to `attribute freight value double`, which correctly models the semantic type.

### Query 262 (resolved)
Previously failed due to `collect()` + `UNWIND` for product co-occurrence. Converted using a self-join on the `orders` relation to find product pairs appearing in the same order, with `$id1 < $id2` to deduplicate pairs.

### Query 399 (resolved)
Previously failed due to `COLLECT()` + `REDUCE` + `RANGE` + `SIZE()` for computing cumulative price variation. Converted using `max_order_price()` and `min_order_price()` custom functions on the `order_unit_price` attribute of the `orders` relation, computing variation as `$max - $min`.

### Query 689 (resolved)
Previously failed due to schema mismatch (no `Employee` entity or `PROCESSED` relation). Converted to return distinct `employee_id` values from orders placed by the specified customer, which is the closest available data in the schema.
