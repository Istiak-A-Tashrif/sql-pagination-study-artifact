# Revision 1 experiments (SUJ review of MANS-SUJ-62-02-26)

New evidence requested by the reviewer: stronger baselines, non-unique and aggregate orderings, independent sessions and repeated plans. The frozen design is in PROTOCOL.md; the primary (../) and follow-up (../extensions/) collections are unchanged.

## Reproduce

From the repository root, with Docker Desktop, Node.js 22 and the project virtual environment:

```sh
python3 backend-study/revision/run.py                 # guarded collection, about 60 minutes
.venv/bin/python backend-study/revision/analyze.py    # audits and statistics -> results/derived/revision.json
.venv/bin/python backend-study/revision/report.py     # figures and manuscript values
.venv/bin/python backend-study/analyze.py             # original-collection analysis; merges all manuscript values
```

`run.py` operates only on Compose project `unibackendr` (ports 24004/25435) and refuses to start while the main research driver is running. `analyze.py` accepts only a fully accepted collection; `PARTIAL=1` performs a dry run over completed sessions.

## Files

- `src/queries.cjs`: all SQL (7 designs x 4 orderings x 2 pagination methods).
- `src/prepare.cjs`: datasets, materialized view, counter table with triggers, oracle gate, expected page digests and cursors.
- `src/plans.cjs`, `src/writecost.cjs`, `runner.mjs`, `src/server.cjs`: plans, write costs, client and API.
- `results/raw/`: environment, batches with guard state, correctness log, requests/API/trial logs, per-session plans, write-cost log, expected digests.
- `results/derived/`: `revision.json` (cell statistics, ratios, plans, excerpts, cost model), `rev-values.json` (manuscript values), trial means, drift and raw hashes.
