# Semantic Review Notes

## What to Look For

### 1. Property Mismatches
- **"retweeted X times"** vs `favorites > X` - Question asks about retweets but query uses favorites
- **"retweet count"** vs favorites - Same issue, different phrasing
- Watch for any metric name in question that doesn't match the property being filtered

### 2. Relation Direction Issues
- **Passive voice questions** ("tweets that have been retweeted") should match tweets as the *target* of retweets
- **Active voice questions** ("tweets that retweet") should match tweets as the *source* of retweets
- Check: `(a)-[:REL]->(b)` direction vs question intent
- In TypeQL: `relation (role1: $a, role2: $b)` - verify role assignments match semantics

### 3. Entity Return Mismatches
- **"tweets from users who follow X"** should return tweets by followers, not tweets by X
- **"users who have amplified"** (active) vs "users who have been amplified" (passive)
- Check: What entity does the question ask about vs what the query returns

### 4. Missing Aggregation Components
- **"total interactions (mentions, retweets, replies)"** - must include ALL three, not just one
- **"favorites AND retweets"** - both must be aggregated
- Check: Does the TypeQL include all components mentioned in the question?

### 5. Missing Filter Constraints
- **"follow both X and Y"** - must have two follows relations
- **"mentioned AND retweeted"** - both conditions required
- Check: Does the TypeQL enforce all constraints from the question?

### 6. Wrong Relation Type
- **"users that X retweeted"** using AMPLIFIES instead of RETWEETS
- Check: Is the relation type semantically correct for what's being asked?

### 7. OPTIONAL MATCH / Disjunction Patterns (OR logic)
- Cypher `OPTIONAL MATCH` creates left-outer-join semantics (include rows even if pattern doesn't match)
- Multiple `OPTIONAL MATCH` clauses for different interaction types need `or` or `try` in TypeQL
- Example: "tweets with mentions OR retweets OR replies"
- TypeQL options:
  - `or { pattern1; } or { pattern2; }` - explicit disjunction (at least one must match)
  - `try { pattern; }` - optional pattern (may or may not match, for left-join semantics)

**Detection patterns in Cypher:**
- `OPTIONAL MATCH` keyword
- `UNION` (combines result sets)
- `COALESCE` (null handling often paired with OPTIONAL)
- Multiple `exists` checks combined
- Questions mentioning "X OR Y", "either", "any of"
- Questions about "total" of multiple interaction types (mentions + retweets + replies)

### 8. Existence Checks
- Cypher `WHERE exists { (pattern) }` checks if pattern exists
- TypeQL handles this naturally by including the pattern in match
- But `NOT exists` needs `not { pattern; }` in TypeQL

### 9. Aggregation After Grouping
- Cypher `WITH ... WHERE count > N` filters after aggregation (HAVING equivalent)
- TypeDB supports this via chained reduce: `reduce $c = count groupby $x; match $c > N;`

### 10. String Length Checks (TypeDB 3.8+)
- Cypher `size(n.prop)` for string length → TypeQL `let $len = len($prop);`
- Only applies to **string** attributes, not collections/lists
- Example: `WHERE size(m.tagline) > 30` → `$m has tagline $t; let $len = len($t); $len > 30;`

## OPTIONAL MATCH Queries by Database

Total: 8 queries across all databases
- twitter: 2 (indices 81, 85 - moved to failed_review)
- twitch: 1 (index 123 - moved to failed_review)
- companies: 2 (not yet converted)
- gameofthrones: 3 (not yet converted)
- movies: 0
- neoflix: 0
- recommendations: 0

## Review Process

1. Read the English question carefully
2. Identify: What entities? What relationships? What filters? What's returned?
3. Compare against the TypeQL:
   - Are the correct entities matched?
   - Are relations in the right direction?
   - Are all filters present?
   - Does the return/fetch match what's asked?
4. Check for OPTIONAL MATCH in Cypher - needs special handling with `try` or `or`
5. Flag mismatches with specific reason
