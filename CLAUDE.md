# Text2TypeQL - Project Notes

## Important: First Steps (Main Session Only)

When starting a **main interactive session** (NOT when running as a subagent), read these files:
- `README.md` - Dataset card and project overview
- `pipeline/README.md` - Pipeline docs, progress, and remaining tasks
- `plan.md` - Implementation plan (if it exists)
- `dataset/<source>/<database>/README.md` - Query counts for each database being worked on

**Subagents** (e.g., `convert-query-runner`) should NOT read these files — they have self-contained instructions.

## Updating Documentation

When learning new TypeQL patterns or syntax rules, update ALL of these files:
- `CLAUDE.md` - This file (quick reference)
- `.claude/skills/convert-query.md` - Conversion skill (comprehensive reference)
- `pipeline/docs/suggestions.md` - Validated examples of advanced patterns

## Project Overview

Pipeline to convert Neo4j text2cypher datasets to TypeQL format for training text-to-TypeQL models.

**Source**: https://github.com/neo4j-labs/text2cypher

Two source datasets:
- **synthetic-1**: `datasets/synthetic_opus_demodbs/` -- 7 databases, 4,776 valid queries (4,733 converted, 43 failed)
- **synthetic-2**: `datasets/synthetic_gpt4o_demodbs/` -- 15 databases, 9,267 valid queries (9,206 converted, 61 failed)

## Important: Sequential Processing

**DO NOT process queries in parallel.** Multiple agents writing to the same CSV file can cause race conditions and data loss. Always process queries one at a time, waiting for each to complete before starting the next.

## Available Skills

Use this skill for query conversion (requires TypeDB server running):

- `/convert-query <database> <index>` - Convert from synthetic-1 (default)
- `/convert-query <database> <index> --source synthetic-2` - Convert from synthetic-2

## Quick Start

```bash
# Start TypeDB server (must be running for validation)
typedb server --development-mode.enabled=true

# Run pipeline
python pipeline/main.py setup                      # Clone Neo4j dataset
python pipeline/main.py list-schemas               # List schemas (synthetic-1)
python pipeline/main.py list-schemas --source synthetic-2  # List schemas (synthetic-2)
python pipeline/main.py convert-schema movies      # Convert schema

# Use skill for query conversion (agent-based, no API costs)
/convert-query movies 0
/convert-query movies 0 --source synthetic-2
```

## Agent-Based Query Conversion (Main Session Only)

**NOTE: This section is for the MAIN interactive session only. If you are a subagent (e.g., `convert-query-runner`), IGNORE this entire section — do the conversion work directly using your own instructions.**

In the main session, always delegate TypeQL query conversion to the `convert-query-runner` subagent. Do NOT write TypeQL queries directly in the main conversation — use the Task tool to spawn the subagent. This ensures consistent validation, semantic review, and CSV routing.

**IMPORTANT: Process queries SEQUENTIALLY, not in parallel.** Parallel writes to the same CSV file can cause race conditions.

Set `max_turns: 15` to prevent runaway execution:
```
Use Task tool with subagent_type=convert-query-runner, max_turns=15
Prompt: "Convert query <index> from the <database> database"
```

For synthetic-2:
```
Prompt: "Convert query <index> from the <database> database --source synthetic-2"
```

When providing hints or specific patterns to use, include them in the subagent prompt:
```
Prompt: "Convert query <index> from <database>. Hint: use reduce with max() groupby for the aggregation."
```

For re-converting queries from `failed_review.csv`:
```
Prompt: "Convert query <index> from <database> --source failed_review"
```

## TypeDB 3.0 Query Syntax

### Key Rules

1. **Query order**: `match` → `sort` → `limit` → `fetch` (or `reduce`)
2. **Relations**: `relation_type (role: $var, role: $var);` (NOT `(role: $var) isa type`)
3. **Fetch directly**: `fetch { "prop": $entity.prop };` - no need to bind
4. **Double quotes** for strings
5. **Grouped counts**: `reduce $count = count($var) groupby $group_var;`

### Pattern Examples

```typeql
# Entity with attribute
$p isa person, has name "John";

# Relation (TypeDB 3.0 style - preferred)
follows (follower: $a, followed: $b);

# Relation with variable (when accessing relation attributes)
$rel isa follows (follower: $a, followed: $b);
$rel has timestamp $t;

# Fetch directly from entity (preferred)
fetch { "name": $p.name, "age": $p.age };

# Bind only when filtering/sorting
$p has age $a; $a > 25;
sort $a desc;
fetch { "age": $a };

# Multi-cardinality attributes
fetch { "emails": [ $p.email ] };

# Negation
not { follows (follower: $p, followed: $other); };

# Grouped aggregation
match $p isa person; acted_in (actor: $p, film: $m);
reduce $count = count($m) groupby $p;
sort $count desc;
limit 5;
```

### Advanced Features

```typeql
# String length (TypeDB 3.8+)
let $len = len($name);

# String concatenation (TypeDB 3.8+)
let $display = $name + " (" + $city + ")";

# Custom functions - reusable query logic
with fun follower_count($user: user) -> integer:
  match follows (followed: $user);
  return count;
match $u isa user;
let $count = follower_count($u);
fetch { "user": $u.name, "followers": $count };

# Chained reduce - HAVING equivalent (filter on aggregation)
match $tweet isa tweet; retweets (original_tweet: $tweet);
reduce $count = count groupby $tweet;
match $count > 100;  # Filter after aggregation
fetch { "tweet": $tweet.text, "retweets": $count };

# Let expressions - computed values
let $ratio = $follows / $followers;
let $difference = abs($a - $b);

# Type variables - polymorphic queries
$rel isa $t;
{ $t label mentions; } or { $t label retweets; };

# Relation role inference - omit roles to match all permutations
$rel isa interacts ($c);  # Matches $c in ANY role (character1 or character2)

# Recursive stream function - transitive closure (replaces [:REL*])
with fun supply_chain($o: organization) -> { organization }:
  match
    {
      supplies (supplier: $s, customer: $o);
    } or {
      let $mid in supply_chain($o);
      supplies (supplier: $s, customer: $mid);
    };
  return { $s };
with fun supply_chain_size($o: organization) -> integer:
  match let $s in supply_chain($o);
  select $s;
  distinct;
  return count;

# Symmetric/bidirectional matching - omit roles for both players
subsidiary_of ($o1, $o2);  # Matches ($o1 as parent, $o2 as child) OR ($o1 as child, $o2 as parent)
# Replaces: { subsidiary_of (parent: $o1, subsidiary: $o2); } or { subsidiary_of (parent: $o2, subsidiary: $o1); };

# Explicit role type checking (when needed)
$rel isa interacts ($role: $c);
{ $role sub interacts:character1; } or { $role sub interacts:character2; };
```

### Variable Scoping in Disjunctions

**IMPORTANT**: Variables inside disjunction branches are scoped and not returned. This affects counting:

```typeql
# WRONG - $rel not accessible outside disjunction, nothing to count
{ interacts (character1: $c); } or { interacts (character2: $c); };
reduce $count = count($rel) groupby $comm;  # Error: $rel undefined

# ALSO WRONG - $rel inside disjunction branches is still scoped!
{ $rel isa interacts ($c); } or { $rel isa interacts1 ($c); };
reduce $count = count($rel) groupby $comm;  # $rel still scoped to branches

# RIGHT - single relation type, bind outside disjunction
$rel isa interacts ($c);
reduce $count = count($rel) groupby $comm;  # Works

# RIGHT - multiple relation types, use TYPE VARIABLE
$rel isa $t ($c);
{ $t label interacts; } or { $t label interacts1; } or { $t label interacts2; };
reduce $count = count($rel) groupby $comm;  # Works - $rel bound outside disjunction
```

### Cypher → TypeQL Mapping

| Cypher | TypeQL 3.0 |
|--------|------------|
| `MATCH (n:Label)` | `match $n isa label;` |
| `MATCH (a)-[:REL]->(b)` | `match rel (role1: $a, role2: $b);` |
| `RETURN n.prop` | `fetch { "prop": $n.prop };` |
| `WHERE n.prop > 5` | `has prop $p; $p > 5;` |
| `WHERE n.prop CONTAINS 'x'` | `has prop $p; $p like ".*x.*";` |
| `ORDER BY n.prop DESC` | `has prop $p; sort $p desc;` |
| `LIMIT 10` | `limit 10;` |
| `COUNT(n)` | `reduce $count = count($n);` |
| `WITH n, count(m) AS c` | `reduce $c = count($m) groupby $n;` |
| `WITH a, b, count(*) AS c` | `reduce $c = count groupby $a, $b;` (tuple groupby) |
| `WITH x, count(y) WHERE c > N` | `reduce $c = count groupby $x; match $c > N;` |
| `count(DISTINCT x) GROUP BY y` | `select $x, $y; distinct; reduce $c = count groupby $y;` |
| `ORDER BY a / b` | `let $ratio = $a / $b; sort $ratio;` |
| `size(n.prop)` (string) | `let $len = len($prop); $len > N;` |
| `a.prop + ' text'` | `let $s = $prop + " text";` |
| `(a)-[:REL*]->(b)` | Recursive stream function (see below) |
| `collect(n.prop)` | Fetch subquery: `"key": [ match ...; fetch { ... }; ]` |
| `timestamp()` (epoch int) | `max()` aggregate as proxy + integer arithmetic |

## Database Names

TypeDB databases are prefixed: `text2typeql_<database>`

**synthetic-1** (7 databases):
- `text2typeql_twitter`
- `text2typeql_twitch`
- `text2typeql_movies`
- `text2typeql_neoflix`
- `text2typeql_recommendations`
- `text2typeql_companies`
- `text2typeql_gameofthrones`

**synthetic-2** (15 databases -- includes all of the above plus):
- `text2typeql_bluesky`
- `text2typeql_buzzoverflow`
- `text2typeql_fincen`
- `text2typeql_grandstack`
- `text2typeql_network`
- `text2typeql_northwind`
- `text2typeql_offshoreleaks`
- `text2typeql_stackoverflow2`

## Semantic Review Process

After conversion, review queries to verify TypeQL matches the English question:

### Review Checklist
1. **Correct entity returned** - Does the question ask for users/tweets/movies? Does query return that?
2. **Relation direction** - "has been retweeted" (passive) vs "retweets" (active)
3. **All conditions present** - "X AND Y" must have both constraints
4. **Correct property** - "retweeted 100 times" should count retweets, not check favorites
5. **OPTIONAL MATCH** - Must use `try { }` for left-join semantics

### Key Files for Review
- **Full guidance**: `pipeline/docs/semantic_review_notes.md`
- **Move helper**: `python3 pipeline/scripts/review_helper.py <database> <index1> [index2...] --reason "reason" --source <source>`

### Common Semantic Mismatches
| Question Pattern | Common Mistake | Correct Approach |
|------------------|----------------|------------------|
| "retweeted X times" | Using `favorites` property | Count `retweets` relation |
| "tweets that have been retweeted" | Tweet as `retweeting_tweet` | Tweet as `original_tweet` |
| "users who amplified" | Wrong direction | Check `amplifier` vs `amplified_user` roles |
| "tweets from followers" | Tweets by Me | Tweets by users who follow Me |
| OPTIONAL MATCH | Require relation | Use `try { relation; }` |

## File Structure & Workflow

### Dataset Files (per database)

Each `dataset/<source>/<database>/` folder contains:

| File | Purpose | Format |
|------|---------|--------|
| `schema.tql` | TypeQL schema definition | TypeQL |
| `neo4j_schema.json` | Original Neo4j schema | JSON |
| `README.md` | Dataset status, failed queries (with Cypher + reason), and Cypher error notes | Markdown |
| `queries.csv` | **Successfully validated** TypeQL queries | `original_index,question,cypher,typeql` |
| `failed_review.csv` | Queries that **failed semantic review** (temporary, should be empty) | `original_index,question,cypher,typeql,review_reason` |

### Where Queries Live

Queries are tracked in one of these locations:

1. **`queries.csv`** - Successfully converted, validated, and semantically reviewed queries
2. **`README.md` (Failed Queries section)** - Queries that cannot be converted due to TypeQL limitations (string functions, date arithmetic, array operations, etc.). Each entry includes the query index, original Cypher, and reason for failure.
3. **`failed_review.csv`** (temporary) - Queries pending semantic review fixes. After fixing, queries move to `queries.csv` (success) or the README (unfixable). Should be empty when review is complete.

### Query Count Verification (CRITICAL)

**Before committing any changes**, verify that the total number of queries is preserved. The count of queries in `queries.csv` + failed queries documented in the README + any entries in `failed_review.csv` MUST equal the total in the original dataset.

Each README has a verification line like: `Total: 929 + 4 = 933 ✓`

### Retry Workflow

When retrying a previously failed query:
1. Attempt conversion using `/convert-query` skill
2. Validate against TypeDB
3. If **success**: Add to `queries.csv`, update README (remove from Failed Queries, update count)
4. If **failure**: Document in README's Failed Queries section with the Cypher and reason

### Scripts

**CRITICAL: Never read entire CSV files.** Use these scripts to prevent context overflow:

```
pipeline/scripts/
  get_query.py           # Get source query by database and index (--source)
  csv_read_row.py        # Read single row from CSV by original_index
  csv_append_row.py      # Append row to CSV (creates with header if needed)
  csv_move_row.py        # Move row between CSVs atomically
  review_helper.py       # Move queries during review (--source)
```

**CSV Script Usage:**
```bash
# Check if query already processed
python3 pipeline/scripts/csv_read_row.py dataset/<source>/<db>/queries.csv <index> --exists

# Append successful conversion
python3 pipeline/scripts/csv_append_row.py dataset/<source>/<db>/queries.csv '{"original_index": N, "question": "...", "cypher": "...", "typeql": "..."}'
```

### Other Files

```
pipeline/docs/
  semantic_review_notes.md  # Full review guidance
  typeql_reference.md       # Comprehensive TypeQL 3.0 reference (read only when needed)

.claude/skills/
  convert-query.md          # Conversion skill (streamlined)
```

## Query Counts by Database

### synthetic-1 (opus) -- fully converted

| Database | Total Queries | Converted | Failed |
|----------|--------------|-----------|--------|
| twitter | 493 | 491 | 2 |
| twitch | 561 | 554 | 7 |
| movies | 729 | 726 | 3 |
| neoflix | 915 | 910 | 5 |
| recommendations | 753 | 741 | 12 |
| companies | 933 | 930 | 3 |
| gameofthrones | 392 | 381 | 11 |
| **Total** | **4776** | **4733** | **43** |

### synthetic-2 (gpt4o) -- fully converted

| Database | Valid Queries | Converted | Failed |
|----------|-------------|-----------|--------|
| bluesky | 135 | 135 | 0 |
| buzzoverflow | 592 | 585 | 7 |
| companies | 966 | 966 | 0 |
| fincen | 614 | 609 | 5 |
| gameofthrones | 393 | 384 | 9 |
| grandstack | 807 | 805 | 2 |
| movies | 738 | 737 | 1 |
| neoflix | 923 | 916 | 7 |
| network | 625 | 620 | 5 |
| northwind | 807 | 807 | 0 |
| offshoreleaks | 507 | 498 | 9 |
| recommendations | 775 | 764 | 11 |
| stackoverflow2 | 307 | 306 | 1 |
| twitch | 576 | 572 | 4 |
| twitter | 502 | 502 | 0 |
| **Total** | **9267** | **9206** | **61** |
