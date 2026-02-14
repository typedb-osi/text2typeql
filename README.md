# Text2TypeQL

13,939 natural-language questions paired with validated TypeQL 3.0 queries across 15 domains (4,733 from synthetic-1, 9,206 from synthetic-2).

## Overview

Foundation models generate SQL and Cypher reasonably well thanks to large public corpora and benchmark datasets. TypeQL 3.0, released with TypeDB 3.0, has little of that, and relies mostly on being close to natural language. Even frontier models struggle to produce correct queries without expensive reasoning sequences and context-heavy prompting. This dataset addresses that gap.

**Text2TypeQL** provides supervised training data for fine-tuning models on TypeQL generation, a retrieval corpus for few-shot prompting and RAG, and a standardized evaluation benchmark for TypeQL generation quality. Each entry includes the English question, the original Cypher query (from the source dataset), and a validated TypeQL 3.0 query. TypeQL schemas model the domains. Schemas were generated according to the loose Neo4j schema provided, and tweaked throughout the query generation process.

The dataset was produced by converting Neo4j Labs' [text2cypher](https://github.com/neo4j-labs/text2cypher) dataset, which itself was generated using AI. It was created using agents operating under a detailed TypeQL 3.0 reference, with every query validated against a live TypeDB instance and semantically reviewed to verify it correctly answers the English question. About 5-10% of remaining queries were then manually prompted with extra information.

Interestingly, an automated scan of all converted query pairs found that **597 Cypher queries (4.3%)** contain semantic errors that TypeDB's type system either prevented or corrected during conversion — reversed relation directions (198), incorrect property shortcuts for relationship counts (180), wrong property ownership (160), and schema hallucinations (59). These were not TypeQL bugs — the Cypher itself was wrong, and Neo4j's looser schema model allowed the errors to go undetected. See the [full analysis](docs/neo_semantic_analysis/).

## Source Datasets

Two Neo4j text2cypher source datasets are used:

| Source | Neo4j Directory | Databases | Valid Queries | Status |
|--------|----------------|-----------|---------------|--------|
| `synthetic-1` | `synthetic_opus_demodbs` | 7 | 4,776 | 4,733 converted (43 failed) |
| `synthetic-2` | `synthetic_gpt4o_demodbs` | 15 | 9,267 | 9,206 converted (61 failed) |

## Domains

### synthetic-1 (fully converted)

| Domain | Queries | Description |
|--------|---------|-------------|
| [twitter](dataset/synthetic-1/twitter/) | 491 | Users, tweets, hashtags, retweets, follows |
| [twitch](dataset/synthetic-1/twitch/) | 554 | Streamers, games, teams, subscriptions |
| [movies](dataset/synthetic-1/movies/) | 726 | Actors, directors, producers, reviews, roles |
| [neoflix](dataset/synthetic-1/neoflix/) | 910 | Movies, ratings, genres, subscriptions |
| [recommendations](dataset/synthetic-1/recommendations/) | 741 | Users, movies, genres, ratings, actors |
| [companies](dataset/synthetic-1/companies/) | 930 | Organizations, subsidiaries, CEOs, articles |
| [gameofthrones](dataset/synthetic-1/gameofthrones/) | 381 | Characters, houses, battles, interactions |
| **Total** | **4,733** | + 43 documented failures |

### synthetic-2 (fully converted)

| Domain | Total | Converted | Description |
|--------|-------|-----------|-------------|
| [bluesky](dataset/synthetic-2/bluesky/) | 135 | 135 | Social network posts and interactions |
| [buzzoverflow](dataset/synthetic-2/buzzoverflow/) | 592 | 585 | Q&A platform (Stack Overflow-like) |
| [companies](dataset/synthetic-2/companies/) | 966 | 966 | Organizations, subsidiaries, CEOs, articles |
| [fincen](dataset/synthetic-2/fincen/) | 614 | 609 | Financial crime reports and filings |
| [gameofthrones](dataset/synthetic-2/gameofthrones/) | 393 | 384 | Characters, houses, battles, interactions |
| [grandstack](dataset/synthetic-2/grandstack/) | 807 | 805 | Movie reviews (GRANDstack demo) |
| [movies](dataset/synthetic-2/movies/) | 738 | 737 | Actors, directors, producers, reviews, roles |
| [neoflix](dataset/synthetic-2/neoflix/) | 923 | 916 | Movies, ratings, genres, subscriptions |
| [network](dataset/synthetic-2/network/) | 625 | 620 | Computer network topology |
| [northwind](dataset/synthetic-2/northwind/) | 807 | 807 | Products, orders, suppliers (Northwind) |
| [offshoreleaks](dataset/synthetic-2/offshoreleaks/) | 507 | 498 | Offshore financial entities |
| [recommendations](dataset/synthetic-2/recommendations/) | 775 | 764 | Users, movies, genres, ratings, actors |
| [stackoverflow2](dataset/synthetic-2/stackoverflow2/) | 307 | 306 | Q&A platform variant |
| [twitch](dataset/synthetic-2/twitch/) | 576 | 572 | Streamers, games, teams, subscriptions |
| [twitter](dataset/synthetic-2/twitter/) | 502 | 502 | Users, tweets, hashtags, retweets, follows |
| **Total** | **9,267** | **9,206** | + 61 documented failures |

## Data Format

### Merged dataset

`dataset/synthetic-1/all_queries.csv` contains all converted queries for synthetic-1:

| Column | Description |
|--------|-------------|
| `domain` | Database domain name |
| `original_index` | Index in the source dataset |
| `question` | Natural-language question |
| `cypher` | Original Cypher query |
| `typeql` | Validated TypeQL 3.0 query |

### Per-domain files

Each `dataset/<source>/<domain>/` directory contains:

- `schema.tql` -- TypeQL schema definition
- `queries.csv` -- Query pairs (`original_index`, `question`, `cypher`, `typeql`)
- `neo4j_schema.json` -- Original Neo4j schema
- `README.md` -- Domain stats, failed queries with reasons, and Cypher errors found

## Usage

```python
import pandas as pd

# Load all synthetic-1 queries
df = pd.read_csv("dataset/synthetic-1/all_queries.csv")

# Filter by domain
twitter = df[df["domain"] == "twitter"]

# Load a single domain
movies = pd.read_csv("dataset/synthetic-1/movies/queries.csv")
```

## What the Type System Caught

An automated scan of all 13,939 converted query pairs found that **597 Cypher queries (4.3%)** contain semantic errors that TypeDB's type system either prevented or corrected during conversion. These are not TypeQL bugs — the Cypher itself was wrong, and Cypher's looser schema model allowed the errors to go undetected.

| Error Category | Queries | Root Cause |
|----------------|--------:|------------|
| Direction errors | 198 | Arrow syntax detached from semantics; role names eliminate ambiguity |
| Counting errors | 180 | Denormalized property shortcuts; TypeQL forces explicit relation counting |
| Property errors | 160 | Silent null on missing properties; TypeQL validates attribute ownership |
| Hallucinated relations | 28 | No schema validation at query time; TypeQL rejects unknown relation types |
| Hallucinated properties | 19 | Same as above; TypeQL rejects undeclared attributes |
| Hallucinated labels | 12 | Same as above; TypeQL rejects undeclared entity types |

An additional 640 queries have Cypher generation issues (missing aggregations, thresholds, etc.) attributable to LLM quality rather than language-structural differences.

In each case the TypeQL was written to correctly answer the English question. See the [full analysis](docs/neo_semantic_analysis/) and each domain's README.

## Failed Queries

104 of 14,043 source queries (0.7%) cannot be expressed in TypeQL 3.0 (43 from synthetic-1, 61 from synthetic-2). They require features not yet supported: `split()`/`size()` for string/list operations, array indexing, epoch timestamp conversion, date component extraction (year/month/day-of-week), `collect()` aggregation, and substring matching. Each is documented with its original Cypher and the specific missing capability in the per-domain READMEs.

## TODO

- [x] Merge synthetic-2 queries into all_queries.csv
- [ ] Standardize use of `_` in TypeQL variable names across all queries
- [ ] Regularize synthetic-1 TypeQL queries to use updated relation syntax: `reltype (role: $var)` instead of `$r (role: $var) isa reltype`

## Source

Derived from Neo4j Labs' [text2cypher](https://github.com/neo4j-labs/text2cypher) benchmark (`datasets/synthetic_opus_demodbs/` and `datasets/synthetic_gpt4o_demodbs/`). Full credit to Neo4j Labs for creating and open-sourcing the original dataset.

## Conversion Pipeline

See [pipeline/](pipeline/) for the tooling used to produce this dataset, including schema conversion, AI-agent query conversion, TypeDB validation, and semantic review.

## Citation

```bibtex
@software{text2typeql,
  title  = {Text2TypeQL: Natural Language to TypeQL 3.0 Query Dataset},
  year   = {2025},
  url    = {https://github.com/typedb-osi/text2typeql},
  note   = {13,930 validated query pairs across 15 domains, derived from Neo4j Labs text2cypher}
}
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).
