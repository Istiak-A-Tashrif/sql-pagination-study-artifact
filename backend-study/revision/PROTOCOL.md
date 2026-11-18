# Revision experiments: frozen protocol

These experiments answer the SUJ review of manuscript MANS-SUJ-62-02-26. They add stronger baselines, aggregate and non-unique orderings, independent sessions and repeated plans to the primary study (../PROTOCOL.md) and the follow-up study (../extensions/PROTOCOL.md). Neither earlier collection is changed or re-analysed here. Cells, seeds and trial orders are fixed in `build_manifest.py` / `manifest.json` (seed 20261118) before collection.

Isolated Compose project `unibackendr`, own database volume, loopback ports 24004 (API) and 25435 (PostgreSQL). Same PostgreSQL 17.2, Node 22.23.0 image and primary settings (shared_buffers 512 MB, work_mem 16 MB, JIT off, no parallel workers, track_io_timing on). One API pool connection, one sequential client. No Redis.

## Datasets and structures

`s5000`, `s25000`, `s100000`: cloned exactly as in the primary study. `skew100000`: the follow-up study's heavy-tailed generator (`setseed(0.20261022)`). `s100000` additionally has an index on `products(price, id)`.

Every schema has two precomputed-aggregate structures:

- `stats_mv`: a materialized view of (product_id, distinct-order count, mean rating) with a unique index on product_id and indexes on (total_orders, product_id) and (avg_rating, product_id). It is stale between explicit refreshes.
- `products_c`: a copy of products carrying `total_orders` and `avg_rating` columns, kept current by AFTER row triggers on order_items and reviews that recompute both aggregates for the affected product, with indexes on (total_orders, id) and (avg_rating, id).

## Designs

| Design | Description |
|---|---|
| global | Primary global pre-aggregation (unchanged SQL shape) |
| global_hash | Global aggregation rewritten as two-level GROUP BY so the distinct-order count can be hash-aggregated |
| global_pushdown | Keyset only: the cursor predicate is also written inside both child aggregates |
| page_grouped, page_lateral | Primary page-first designs |
| mv | Page selected from the materialized view (MATERIALIZED CTE), then joined |
| counter | Page selected from the counter-column table (MATERIALIZED CTE), then joined |

Orderings: `id` (unique primary key, as in the primary study); `price` (non-unique product column, ID tie-breaker, ascending); `orders` and `rating` (aggregates, descending, ID tie-breaker descending). For aggregate orderings no page can be selected before the aggregates are known, so only global, mv and counter are defined. Keyset uses a row comparison on (sort value, id) and receives the already-known cursor of the preceding row.

## Matrix (156 cells, page size 25)

| Id | Cells |
|---|---|
| R1_baselines | s100000 and skew100000, ID order: 6 designs x {OFFSET, keyset} + global_pushdown keyset, depths 0/50/95% (78) |
| R2_scale | s5000 and s25000: global, page_grouped, page_lateral x 2 methods, 95% (12) |
| R3_aggregate_order | s100000 by orders, s100000 by rating, skew100000 by orders: global, mv, counter x 2 methods x 3 depths (54) |
| R4_price_order | s100000 by price: global, page_grouped, page_lateral x 2 methods x 0/95% (12) |

## Independent sessions

Five sessions. Before each session, the API and PostgreSQL containers are stopped and started again (new postmaster with empty shared buffers, new Node process, new pool connection). Each session has its own shuffled order (seed 20261118 + session), two untimed warm-up requests per cell, then ten three-request trials per cell. Docker's VM page cache is not dropped. After measurement, each session runs EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) three times per cell (15 plans per cell in total).

## Correctness

Before timing, each of the 124 defined design/ordering/method combinations in every schema must match a scalar correlated-subquery oracle, sorted by the same ordering, over the complete result and over page sizes 10/25/100 at depths 0/50/95% (9 windows). During measurement every response digest must equal the oracle digest for its window; a mismatch aborts the collection.

## Write cost (after all sessions, s100000)

400 transactions, alternating with and without row triggers (`session_replication_role = replica`), each inserting one order item and one review for the same product and then rolling back; the counter row's currency is checked inside each triggered transaction. Five `REFRESH MATERIALIZED VIEW` and five `REFRESH MATERIALIZED VIEW CONCURRENTLY` executions. The counter table is hashed before and after to confirm that no state changed.

## Statistics

Unit: three-request trial mean. Within a session: cell mean with 10,000-resample percentile bootstrap. Across sessions: cell mean of session means. Ratio estimates: the ratio of the pooled means; a 95% interval from a two-stage (session, then trial) bootstrap, and a t interval on the five per-session log ratios. No outlier deletion. Only a fully accepted collection is analysed.

## Integrity

Same fail-closed guard as the primary study: before each stage and every 250 ms during it, no main research driver may be running, and only `unibackendr` containers are stopped on abort.
