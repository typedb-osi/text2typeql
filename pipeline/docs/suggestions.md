# Handwritten TypeQL Suggestions for Failed Queries

These are manually crafted TypeQL queries for Cypher queries that couldn't be auto-converted due to TypeDB limitations. These use advanced TypeQL features like custom functions, chained reduce stages, and type variables.

**All queries validated against TypeDB 3.0** ✓

---

## Twitter Dataset

### Index 136

**Question:** List the tweets by 'neo4j' that have been retweeted by more than 5 different users.

**Cypher:**
```cypher
MATCH (me:Me {screen_name: 'neo4j'})-[:POSTS]->(tweet:Tweet)
WHERE count{(tweet)<-[:RETWEETS]-(:Tweet)<-[:POSTS]-(:User)} > 5
RETURN tweet.text, count{(tweet)<-[:RETWEETS]-(:Tweet)<-[:POSTS]-(:User)} AS retweets
```

**TypeQL (validated):**
```typeql
with fun retweeting_users($tweet: tweet) -> integer:
  match
    retweets (original_tweet: $tweet, retweeting_tweet: $retweet);
    posts ($user, $retweet);
  select $user;
  distinct;
  return count;
match
$u isa user, has screen_name 'neo4j';
posts ($user, $tweet);
let $retweeting_users = retweeting_users($tweet);
$retweeting_users > 5;
fetch {
  "tweet": $tweet.text
};
```

---

### Index 295

**Question:** Show all hashtags that have appeared in more than 5 tweets mentioning 'Neo4j'.

**Cypher:**
```cypher
MATCH (t:Tweet)-[:MENTIONS]->(:User {screen_name: 'neo4j'})-[:POSTS]->(tweet:Tweet)-[:TAGS]->(h:Hashtag)
WITH h, count(tweet) AS tweet_count
WHERE tweet_count > 5
RETURN h.name AS hashtag, tweet_count
ORDER BY tweet_count DESC
```

**TypeQL (validated):**
```typeql
match
  $tweet isa tweet, has text $text;
  $text like ".*Neo4j.*";
  tags (tagged_tweet: $tweet, tag: $tag);
reduce $count = count groupby $tag;
match
  $count > 5;
fetch {
  "tag": $tag.hashtag_name,
  "appearances_with_neo4j": $count
};
```

*Fix applied: Changed `contains text` to `has text`*

---

### Index 296

**Question:** List the top 5 users who have a similar betweenness to 'Neo4j'.

**Cypher:**
```cypher
MATCH (me:Me {name: 'Neo4j'}), (u:User)
WHERE u.betweenness IS NOT NULL
WITH me, u
ORDER BY abs(me.betweenness - u.betweenness)
LIMIT 5
RETURN u.name AS user, u.betweenness AS betweenness
```

**TypeQL (validated):**
```typeql
match
$neo4j isa me, has name "Neo4j", has betweenness $neo4j_betweenness;
$user isa user, has betweenness $betweenness;
not { $neo4j is $user; };
let $difference = abs($betweenness - $neo4j_betweenness);
sort $difference asc;
limit 5;
fetch {
  "user": $user.name
};
```

*Fixes applied: Changed hyphenated variable `$neo4j-betweenness` to `$neo4j_betweenness`, changed `sort desc` to `sort asc` (smallest difference = most similar)*

---

### Index 330

**Question:** Which users have the highest following to follower ratio?

**Cypher:**
```cypher
MATCH (u:User)
WHERE u.followers IS NOT NULL AND u.following IS NOT NULL
RETURN u.screen_name AS user,
       toFloat(u.following) / u.followers AS followingToFollowerRatio
ORDER BY followingToFollowerRatio DESC
LIMIT 10
```

**TypeQL (validated):**
```typeql
with fun follower_count($user: user) -> integer:
  match follows (followed: $user);
  return count;
with fun follows_count($user: user) -> integer:
  match follows (follower: $user);
  return count;
match
$user isa user;
let $followers = follower_count($user);
let $follows = follows_count($user);
$followers > 0;
$follows > 0;
let $ratio = $follows / $followers;
sort $ratio desc;
limit 10;
fetch {
  "user": $user.name,
  "ratio": $ratio
};
```

---

### Index 49

**Question:** What are the 3 most common hashtags in tweets that have been retweeted more than 100 times?

**Notes:** The Neo4j query is wrong (uses favorites instead of retweet count)!

**Cypher:**
```cypher
MATCH (t:Tweet)-[:TAGS]->(h:Hashtag)
WHERE t.favorites > 100
RETURN h.name AS hashtag, count(*) AS count
ORDER BY count DESC
LIMIT 3
```

**TypeQL (validated):**
```typeql
match
$tweet isa tweet;
retweets (original_tweet: $tweet, retweeting_tweet: $retweet);
reduce $count = count groupby $tweet;
match
$count > 100;
tags (tagged_tweet: $tweet, tag: $hashtag);
reduce $hashtag_count = count groupby $hashtag;
sort $hashtag_count desc;
limit 3;
fetch {
  "hashtag": $hashtag.hashtag_name,
  "count": $hashtag_count
};
```

---

### Index 81

**Question:** List the top 5 tweets by the total interaction (mentions, retweets, replies).

**Cypher:**
```cypher
MATCH (t:Tweet)
OPTIONAL MATCH (t)<-[:MENTIONS]-(mention)
OPTIONAL MATCH (t)<-[:RETWEETS]-(retweet)
OPTIONAL MATCH (t)<-[:REPLY_TO]-(reply)
RETURN t.text AS tweet,
       count(mention) AS mentions,
       count(retweet) AS retweets,
       count(reply) AS replies,
       (count(mention) + count(retweet) + count(reply)) AS totalInteractions
ORDER BY totalInteractions DESC
LIMIT 5
```

**TypeQL (validated):**
```typeql
match
$tweet isa tweet;
$rel isa $t;
{
  $t label mentions;
  $rel links (source_tweet: $tweet);
} or {
  $t label retweets;
  $rel links (original_tweet: $tweet);
} or {
  $t label reply_to;
  $rel links (original_tweet: $tweet);
};
reduce $count = count groupby $tweet;
sort $count desc;
limit 5;
fetch {
  "tweet": $tweet.text,
  "count": $count
};
```

*Fix applied: Added `groupby $tweet` to reduce*

---

### Index 85

**Question:** Which 3 tweets have the highest aggregation of favorites and retweets?

**Cypher:**
```cypher
MATCH (t:Tweet)
OPTIONAL MATCH (t)-[:RETWEETS]->(r:Tweet)
RETURN t, t.favorites + count(r) AS score
ORDER BY score DESC
LIMIT 3
```

**TypeQL (validated):**
```typeql
match
$tweet isa tweet;
retweets (original_tweet: $tweet);
reduce $retweets = count groupby $tweet;
match
$tweet has favorites $favorites;
let $total = $favorites + $retweets;
sort $total desc;
limit 3;
fetch {
  "tweet": $tweet.text,
  "total": $total
};
```

---

## Companies Dataset (synthetic-2)

### Index 662: Recursive transitive closure (variable-length path)

**Question:** Which 3 organizations have the most complex supply chains according to the database?

**Cypher:**
```cypher
MATCH (o:Organization)-[:HAS_SUPPLIER*]->(s:Organization)
WITH o, COUNT(DISTINCT s) AS supplierCount
RETURN o.name AS organization, supplierCount
ORDER BY supplierCount DESC
LIMIT 3
```

**TypeQL (validated):**
```typeql
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
match
$o isa organization;
let $count = supply_chain_size($o);
sort $count desc;
limit 3;
fetch {
  "organization": $o.name,
  "supply_chain_size": $count
};
```

**Key pattern:** Recursive stream function replaces Cypher `[:REL*]` variable-length paths. The stream function `supply_chain` returns all reachable nodes via base case (direct relation) + recursive case (disjunction). A second function counts distinct results. TypeDB tables recursive calls to break cycles.

---

## Stack Overflow 2 Dataset

### Index 253: Fetch subquery (replacing collect)

**Question:** List the 3 questions with the highest scores and their associated tags.

**Cypher:**
```cypher
MATCH (q:Question)-[:TAGGED]->(t:Tag)
WITH q, t
ORDER BY q.view_count DESC
LIMIT 3
RETURN q.title AS question_title, q.view_count AS view_count, collect(t.name) AS tags
```

**TypeQL (validated):**
```typeql
match
$q isa question, has view_count $vc;
sort $vc desc;
limit 3;
fetch {
  "question_title": $q.title,
  "view_count": $vc,
  "tags": [
    match
      tagged (question: $q, tag: $t);
    fetch {
      "name": $t.name
    };
  ]
};
```

**Key pattern:** Fetch subquery replaces Cypher `collect()`. The `"key": [ match ...; fetch { ... }; ]` syntax runs an inner query per outer row and collects results as a nested JSON array. The inner `match` can reference variables from the outer query (`$q`).

---

### Index 261: Two-stage aggregation via function pipeline

**Question:** Who are the top 3 users who commented the most on the highest viewed questions?

**Cypher:**
```cypher
MATCH (q:Question)-[:COMMENTED_ON]-(c:Comment)<-[:COMMENTED]-(u:User)
WITH q, u, COUNT(c) AS comment_count
ORDER BY q.view_count DESC
LIMIT 3
WITH u, SUM(comment_count) AS total_comments
RETURN u.display_name AS user, total_comments
ORDER BY total_comments DESC
LIMIT 3
```

**TypeQL (validated):**
```typeql
with fun comment_count_on_top_questions($u: user) -> integer:
  match
    $q isa question, has view_count $vc;
    sort $vc desc;
    limit 3;
    match
      commented_on (comment: $c, question: $q);
      commented (commenter: $u, comment: $c);
    return count;
match
$u isa user;
let $total = comment_count_on_top_questions($u);
$total > 0;
sort $total desc;
limit 3;
fetch {
  "user": $u.display_name,
  "total_comments": $total
};
```

**Key pattern:** Chained `match; sort; limit; match;` inside a function body creates a pipeline: first narrow to top N items, then extend with additional patterns. This replaces Cypher's two-stage `WITH ... ORDER BY ... LIMIT ... WITH ...` CTE pattern.

---

### Index 169: Epoch integer arithmetic for "last year"

**Question:** Which users have asked the most questions in the last year?

**Cypher:**
```cypher
WITH timestamp() AS current_time, timestamp() - 31536000 AS one_year_ago
MATCH (u:User)-[:ASKED]->(q:Question)
WHERE q.creation_date >= one_year_ago
WITH u, COUNT(q) AS question_count
ORDER BY question_count DESC
LIMIT 10
RETURN u.display_name AS user, question_count
```

**TypeQL (validated):**
```typeql
with fun max_creation_date() -> integer:
  match
    $q isa question, has creation_date $cd;
  return max($cd);
match
$u isa user;
asked (asker: $u, question: $q);
$q has creation_date $cd;
let $max_date = max_creation_date();
let $threshold = $max_date - 31536000;
$cd >= $threshold;
reduce $question_count = count($q) groupby $u;
sort $question_count desc;
limit 10;
fetch {
  "user": $u.display_name,
  "question_count": $question_count
};
```

**Key pattern:** When timestamps are stored as epoch integers, use `max()` aggregate as a proxy for "now" and integer arithmetic to compute relative time thresholds. This replaces Cypher's `timestamp()` function.

---

## Twitch Dataset

### Index 360: Recursive stream function for moderator chains

**Question:** Which streams have the longest moderator chains (a moderator, who is also a moderator, and so on)?

**Cypher:**
```cypher
MATCH path = (s:Stream)-[:MODERATOR*]->(u:User)
WITH s, length(path) AS chainLength
ORDER BY chainLength DESC
LIMIT 1
RETURN s.name AS streamName, chainLength
```

**TypeQL (validated):**
```typeql
with fun all_chain_members($s: stream) -> { stream }:
  match
    {
      moderation (moderated_channel: $s, moderating_channel: $next);
    } or {
      let $mid in all_chain_members($s);
      moderation (moderated_channel: $mid, moderating_channel: $next);
    };
  return { $next };
match
$s isa stream;
let $member in all_chain_members($s);
select $s, $member;
distinct;
reduce $chain_length = count($member) groupby $s;
sort $chain_length desc;
limit 1;
fetch {
  "streamName": $s.name,
  "chainLength": $chain_length
};
```

**Key pattern:** Recursive stream function for transitive closure, then count distinct reachable nodes per starting entity to approximate chain/path length. Uses `select; distinct; reduce count groupby` to deduplicate before counting.

---

## Key TypeQL Features Used

1. **Custom functions (`with fun`)** - Define reusable query logic (indices 136, 330)
2. **Chained reduce stages** - `reduce ... match ... reduce ...` for filtering on aggregates (indices 49, 85, 295)
3. **Let expressions** - `let $var = expression` for computed values (indices 85, 296, 330)
4. **Type variables** - `$rel isa $t; $t label typename;` for polymorphic queries (index 81)
5. **Disjunction** - `{ pattern } or { pattern }` for multiple match options (index 81)
6. **Arithmetic** - `$a + $b`, `$a / $b`, `abs($a - $b)` for computed values (indices 85, 296, 330)
7. **Role inference** - `$rel isa relation ($player);` matches player in ANY role (all permutations)
8. **Tuple groupby** - `reduce $c = count groupby $a, $b;` for grouping by multiple variables
9. **String length** (TypeDB 3.8+) - `let $len = len($str);` for `size()` on strings
10. **String concatenation** (TypeDB 3.8+) - `let $s = $a + " " + $b;` for building strings
11. **Datetime subtraction** (TypeDB 3.8+) - `let $diff = $end - $begin;` for duration between two datetime values, supports `sort $diff`
12. **Inline date arithmetic** (TypeDB 3.8+) - `$r >= 2022-01-01T00:00:00 - P365D;` for date literal minus duration in filters
13. **Recursive stream functions** - `with fun f($x: type) -> { type }:` for transitive closure (replaces Cypher `[:REL*]`). Uses `let $var in f($arg);` to access stream, `{ base } or { let $mid in f($arg); recursive; };` for recursion
14. **Fetch subqueries** - `"key": [ match ...; fetch { ... }; ]` runs an inner query per outer row, collecting results as a nested JSON array (replaces Cypher `collect()`)
15. **Function pipelines** - Chained `match; sort; limit; match;` inside function bodies for two-stage aggregation (replaces Cypher CTEs with `WITH ... ORDER BY ... LIMIT ... WITH ...`)
16. **Epoch arithmetic** - `let $threshold = max_func() - 31536000;` for relative time on integer timestamps (replaces Cypher `timestamp()`)

## Important Scoping Rules

**Variables inside disjunction branches are scoped and NOT returned outside:**

```typeql
# WRONG - $rel not accessible, nothing to count
{ interacts (character1: $c); } or { interacts (character2: $c); };
reduce $count = count($rel) groupby $comm;  # Error!

# ALSO WRONG - $rel inside branches is STILL scoped!
{ $rel isa interacts ($c); } or { $rel isa interacts2 ($c); };
reduce $count = count($rel) groupby $comm;  # $rel still scoped!

# RIGHT - single type: bind outside
$rel isa interacts ($c);
reduce $count = count($rel) groupby $comm;  # Works

# RIGHT - multiple types: use TYPE VARIABLE
$rel isa $t ($c);
{ $t label interacts; } or { $t label interacts1; };
reduce $count = count($rel) groupby $comm;  # Works - $rel bound outside
```

**Role inference - omit roles to match all possible role combinations:**

```typeql
# Matches $c in character1 OR character2 role (all permutations)
$rel isa interacts ($c);

# Symmetric/bidirectional - omit roles for BOTH players
subsidiary_of ($o1, $o2);
# Matches: (parent: $o1, subsidiary: $o2) OR (parent: $o2, subsidiary: $o1)
# Much simpler than: { subsidiary_of (parent: $o1, ...); } or { subsidiary_of (parent: $o2, ...); };

# Explicit role type checking when needed
$rel isa interacts ($role: $c);
{ $role sub interacts:character1; } or { $role sub interacts:character2; };
```

## Validation Status

| Index | Status | Notes |
|-------|--------|-------|
| 136 | ✓ Validated | Custom function for counting distinct users |
| 295 | ✓ Validated | Fixed `contains` to `has` |
| 296 | ✓ Validated | Fixed variable naming, sort direction |
| 330 | ✓ Validated | Custom functions for follower/following counts |
| 49 | ✓ Validated | Chained reduce for HAVING-style filter |
| 81 | ✓ Validated | Type variables with disjunction |
| 85 | ✓ Validated | Chained reduce with arithmetic |
| s2/companies 662 | ✓ Validated | Recursive stream function for transitive closure |
| s2/stackoverflow2 253 | ✓ Validated | Fetch subquery replacing collect() |
| s2/stackoverflow2 261 | ✓ Validated | Two-stage aggregation via function pipeline |
| s2/stackoverflow2 169 | ✓ Validated | Epoch integer arithmetic for "last year" |
| s2/twitch 360 | ✓ Validated | Recursive stream function for moderator chains |
