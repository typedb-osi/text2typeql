# Twitter Dataset

**Source:** `synthetic_gpt4o_demodbs` (Neo4j text2cypher)

**Total valid queries: 502**

Tweets, users, follows, retweets, mentions.

## Current Status
- `queries.csv`: 502 converted queries
- 0 failed queries

Total: 502 + 0 = 502 / 502 ✓

## Conversion Notes

Queries 23 and 66 had semantic mismatches in the original Cypher (wrong property used for sorting/filtering) but were successfully converted using TypeQL that correctly implements the English question's intent, matching the same patterns used in synthetic-1.
