# TypeQL 3.0 Reference

## Query Pipeline

```
match <pattern>; → [sort $var;] → [offset N;] → [limit N;] → fetch { } | reduce $var = func();
```

**CRITICAL**: Order must be `match` → `sort` → `offset` → `limit` → `fetch`/`reduce`

## Pattern Matching

### Type Assertion
```typeql
$x isa person;
```

### Attribute Ownership
```typeql
$x has name "John";           # Exact value
$x has age $a;                # Bind to variable
$p isa person, has name $n, has age $a;  # Multiple
```

### Relations (TypeDB 3.0)
```typeql
# Anonymous (preferred)
friendship (friend: $x, friend: $y);
acted_in (actor: $p, film: $m);

# Bound (when need relation attributes)
$rel isa acted_in (actor: $p, film: $m);
$rel has role_name $role;

# Role inference (match any role)
$rel isa interacts ($c);  # $c in ANY role

# Bidirectional (omit both roles)
subsidiary_of ($o1, $o2);  # Matches either direction
```

### Comparisons
```typeql
$p has age $a; $a > 25;
$n like "^John.*";      # Regex
$txt contains "graph";  # Substring
```

| Operator | Purpose |
|----------|---------|
| `==`, `!=` | Equality |
| `<`, `<=`, `>`, `>=` | Ordering |
| `like` | Regex |
| `contains` | Substring |
| `is` | Same instance |

## Logical Operators

### Disjunction (OR)
```typeql
{ $x has status "active"; } or { $x has status "pending"; };
```

### Negation (NOT)
```typeql
not { acted_in (actor: $p, film: $m); };
```

### Optionality (TRY) - for OPTIONAL MATCH
```typeql
$p isa person;
try { $p has nickname $nick; };
```

## Fetch

```typeql
# Direct attribute access (preferred)
fetch { "title": $m.title, "year": $m.released };

# Multi-cardinality (array)
fetch { "emails": [ $p.email ] };

# Fetch subquery (replaces collect() - collects related data as nested array)
fetch {
  "name": $p.name,
  "movies": [
    match
      acted_in (actor: $p, film: $m);
    fetch {
      "title": $m.title
    };
  ]
};
```

## Aggregation

```typeql
# Simple
reduce $count = count($m);

# Grouped
reduce $count = count($m) groupby $n;

# With sort/limit
reduce $count = count($m) groupby $n;
sort $count desc;
limit 10;
```

Functions: `count`, `sum`, `mean`, `max`, `min`

## Advanced Features

### Chained Reduce (HAVING equivalent)
```typeql
reduce $count = count groupby $tweet;
match $count > 100;  # Filter after aggregation
```

### Let Expressions
```typeql
let $ratio = $follows / $followers;
let $diff = abs($a - $b);

# String length (TypeDB 3.8+)
let $len = len($name);

# String concatenation (TypeDB 3.8+)
let $display = $name + " (" + $city + ")";
```

### Select + Distinct (COUNT DISTINCT)
```typeql
select $c, $city;
distinct;
reduce $city_count = count groupby $c;
```

### Type Variables (Polymorphic)
```typeql
$rel isa $t ($c);
{ $t label mentions; } or { $t label retweets; };
reduce $count = count($rel) groupby $c;
```

### Custom Functions
```typeql
with fun follower_count($user: user) -> integer:
  match follows (followed: $user);
  return count;
match $u isa user;
let $count = follower_count($u);
```

### Recursive Stream Functions (Transitive Closure)

Stream functions return zero or more results (indicated by `{ }` in the return type).
Combined with recursion, they replace Cypher's variable-length paths (`[:REL*]`).

```typeql
# Basic transitive closure: find all previous versions
with fun all_previous($v: version) -> { version }:
  match
    {
      previous (newer_version: $v, older_version: $prev);
    } or {
      let $mid in all_previous($v);
      previous (newer_version: $mid, older_version: $prev);
    };
  return { $prev };

# Usage: let $prev in all_previous($start);

# Include starting node with identity base case ($dep is $sw)
with fun all_reachable($sw: software) -> { software }:
  match
    { $dep is $sw; } or
    { depends_on (dependent: $sw, dependency: $dep); $dep isa software; } or
    { let $mid in all_reachable($sw); depends_on (dependent: $mid, dependency: $dep); $dep isa software; };
  return { $dep };

# Count distinct stream results with a wrapper function
with fun chain_size($o: organization) -> integer:
  match let $s in supply_chain($o);
  select $s;
  distinct;
  return count;
```

Key points:
- TypeDB tables recursive functions to break cycles (left-recursive is efficient)
- Results are returned breadth-first (closest nodes first)
- `let $var in function($arg);` accesses stream elements in the main query
- Function parameters must be typed to a specific entity type (no generic `entity` type)

## Variable Scoping in Disjunctions

**CRITICAL**: Variables inside disjunction branches are scoped!

```typeql
# WRONG - $rel not accessible
{ $rel isa interacts ($c); } or { $rel isa interacts2 ($c); };
reduce $count = count($rel);  # Error!

# RIGHT - use type variable
$rel isa $t ($c);
{ $t label interacts; } or { $t label interacts2; };
reduce $count = count($rel);  # Works
```

## Cypher → TypeQL Quick Reference

| Cypher | TypeQL |
|--------|--------|
| `MATCH (n:Label)` | `$n isa label;` |
| `MATCH (a)-[:REL]->(b)` | `rel (role1: $a, role2: $b);` |
| `WHERE n.prop > 5` | `$n has prop $p; $p > 5;` |
| `WHERE a OR b` | `{ a; } or { b; };` |
| `WHERE NOT x` | `not { x; };` |
| `OPTIONAL MATCH` | `try { };` |
| `RETURN n.prop` | `fetch { "prop": $n.prop };` |
| `ORDER BY x DESC` | `sort $x desc;` |
| `LIMIT 10` | `limit 10;` |
| `count(n)` | `reduce $c = count($n);` |
| `WITH n, count(m) AS c` | `reduce $c = count($m) groupby $n;` |
| `HAVING count > N` | `reduce $c = count ...; match $c > N;` |
| `size(n.prop)` (string) | `let $len = len($prop);` |
| `a.prop + ' text'` | `let $s = $prop + " text";` |
| `(a)-[:REL*]->(b)` | Recursive stream function (see above) |
| `CONTAINS 'x'` | `$p contains "x";` |
| `STARTS WITH 'x'` | `$p like "^x.*";` |
| `collect(n.prop)` | Fetch subquery: `"key": [ match ...; fetch { ... }; ]` |
| `timestamp()` (epoch) | `max()` aggregate as proxy + integer arithmetic |

## Unsupported (Document in README)

- `array[N]` - array indexing
- `split()` - string splitting
- `left()` / `substring()` - substring extraction
- `datetime({epochSeconds: N})` - epoch-to-datetime conversion (integer epoch arithmetic works though)
- Dynamic `CONTAINS` between two variables (like requires literal pattern)

Note: `size()` for **string length** is now supported via `len()` (TypeDB 3.8+). `collect()` is now handled via **fetch subqueries** (`"key": [ match ...; fetch { ... }; ]`).
