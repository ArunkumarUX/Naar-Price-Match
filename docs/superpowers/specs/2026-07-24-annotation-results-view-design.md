# Design — Annotation → Finalize → Price-Match Results view

Date: 2026-07-24
Scope: `poc/verify_app.py` (+ `poc/naar_price_poc.py`, new `poc/results_store.py`)
Status: approved in brainstorming; pending spec review

## Problem

`verify_app.py` is a **data-annotation** tool: for each Naar seller (~120) × marketplace
(amazon_in / flipkart / meesho) a human **confirms / rejects / pastes** the seller's real
store, writing `poc/seller_identity.json`. Confirmed stores can then drive a store-first
price-match scan — but today the scan is a separate CLI step and its output is never shown
in the tool. We want the annotation UI to flow into showing the price-match results.

## Decisions (from brainstorming)

1. **Flow = annotate → finalize → results** (one page, a `[ Annotate | Results ]` toggle).
2. **The UI runs the scan live** — a background job with progress, then the results view.
3. **Run scope = all confirmed, with a cost preview** — a preview ("N sellers, P products,
   ~K API calls") precedes the actual (paid) run; one click to proceed.
4. **Results = one filterable table** — product × marketplace rows, defaulting to
   matches-first / sorted by Δ; filters give the "price-gaps" and "per-seller" views without
   separate screens.
5. **Persist + export** — results are stored and reloaded on open; a **Download CSV** button
   produces the shareable sheet.
6. **Storage = SQLite for results** (`poc/results.db`, stdlib `sqlite3`, no external server);
   **annotations stay in `seller_identity.json`** (curated ground-truth, already hardened).

Rejected: separate results app/page (duplicate plumbing); shelling out to the CLI (messier
progress than an in-process call); Postgres (couples the standalone POC to the app stack).

## Architecture & data flow

```
verify_app.py — one server, one page, two views
  Annotate view (existing)  → writes seller_identity.json      (the annotations)
     │  toggle ▸ [ Annotate | Results ]
  Results view (new)
     Finalize & run → preview (N sellers, P products, ~K calls)
                    → confirm → background job (one at a time)
                    → progress (poll done/total)
                    → table (product×market rows, Δ, status, filter, paginate)
                    → Download CSV

engine (naar_price_poc.py, reused + new):
  confirmed_scan_plan(products, marketplaces) -> plan     # NO network (preview)
  scan_confirmed(plan, adapters, progress_cb) -> [Record] # reuses compare_variant
results_store.py (new, stdlib sqlite3):
  save_run(records, meta) -> run_id ; query_results(...) ; latest_run() ; list_runs()
```

Input = annotations (`seller_identity.json`) + the Naar catalogue. A run matches only
**confirmed** (seller, marketplace) pairs, writes a `run` + its `result` rows to SQLite. The
Results view loads the **latest run** on open (persists across restarts), filters/sorts/pages
it in SQL, and exports it as CSV.

## Storage & schema (SQLite: `poc/results.db`, gitignored)

Split by data nature: **annotations = file** (curated, git-diffable, hardened atomic write +
lock + corrupt-backup — untouched); **results = DB** (machine-generated, accumulate across
runs, benefit from querying).

```sql
run(
  id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,
  status TEXT,                                   -- running | done | error
  total INT, done INT, seller_count INT, product_count INT,
  api_calls_est INT, error TEXT
)
result(
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES run(id),
  naar_seller_id, naar_seller_name, naar_product_id, naar_product_title,
  naar_variant_id, naar_variant_name, marketplace, status,
  naar_selling_price REAL, marketplace_selling_price REAL, marketplace_unit_price REAL,
  qty_ratio REAL, marketplace_sold_by, mrp_displayed REAL, other_sellers,
  listing_id, listing_url, match_evidence, observed_at
)
-- indexes: result(run_id), result(status), result(naar_seller_id)
```

`result` columns mirror the `Record` dataclass verbatim (`dataclasses.asdict` → row) so there
is no mapping drift. Open the DB in **WAL** mode with a short busy-timeout (background writer
vs UI reader). New module `poc/results_store.py`, unit-tested via `sqlite3 :memory:`:

- `init_db(path)`
- `save_run(records: list[Record], meta: dict) -> int`  (run_id)
- `latest_run() -> dict | None`, `list_runs() -> list[dict]`
- `query_results(run_id, status=None, seller=None, order="matches_first", limit, offset) -> (rows, total)`

## Engine: `confirmed_scan_plan` + `scan_confirmed` (in `naar_price_poc.py`)

Separate the **free preview** from the **paid run**:

```python
def confirmed_scan_plan(products, marketplaces) -> dict:
    """Cost preview — NO network. Reads registry + catalogue only.
    A 'pair' = one (product, variant, confirmed-marketplace)."""
    # for each product whose sellerId is CONFIRMED on >=1 marketplace,
    # expand variants x that seller's confirmed marketplaces
    return {"sellers": M, "products": P, "pairs": K, "api_calls_est": E,
            "plan": [(product, variant, marketplace, store), ...]}

def scan_confirmed(plan, adapters, progress_cb=None, llm_judge=False, strict=False) -> list[Record]:
    """Store-first run over the plan. Reuses compare_variant + _confirmed_store,
    with per-pair try/except isolation (one bad row never aborts) and the honest
    MATCHED / PRODUCT_NOT_FOUND / OUT_OF_STOCK / SOURCE_ERROR statuses."""
    total = len(plan)
    records = []
    for i, (product, variant, mkt, store) in enumerate(plan):
        try:
            rec = compare_variant(product, variant, adapters[mkt], llm_judge, strict, store=store)
        except Exception as e:               # defence in depth; compare_variant already guards
            rec = Record(product.get("_id",""), variant.get("_id",""),
                         product.get("sellerId",""), mkt, "SOURCE_ERROR",
                         match_evidence=f"{type(e).__name__}: {e}")
        records.append(rec)
        if progress_cb:
            progress_cb(i + 1, total)
    return records
```

- **Preview is instant and free** — computed from the cached catalogue + registry, zero
  ScraperAPI calls. It powers the confirm step.
- **`api_calls_est`** ≈ pairs × (1 search + ~N product fetches); labeled an *estimate*.
- `progress_cb` is the only new seam; the engine stays web-agnostic and unit-testable with
  fixture adapters (no network).

## Endpoints + background-job state (`verify_app.py`)

One job at a time; same background-thread + poll pattern as the existing seller load.

```python
_job = {"status": "idle|running|done|error", "done": 0, "total": 0,
        "run_id": None, "started": "", "error": ""}          # guarded by _job_lock
```

| Endpoint | Behaviour |
|---|---|
| `GET /api/run/preview` | `confirmed_scan_plan` → `{sellers, products, pairs, api_calls_est}` — instant, no network |
| `POST /api/run` | job running → **409**; else spawn thread: build plan → `scan_confirmed(progress_cb → _job)` → `save_run()` → `status=done`/`error`. Returns `{started: true}` |
| `GET /api/run/status` | `_job` snapshot (`status, done, total, run_id, error`), polled ~1.5s |
| `GET /api/results?run_id&status&seller&order&page` | `query_results` (latest run if `run_id` omitted) → `{rows, total, run}` — SQL-side filter/sort/paginate |
| `GET /api/results/export.csv?run_id` | `make_sheet` columns from the run's rows → CSV download (`Content-Disposition: attachment`) |
| `GET /api/runs` | `list_runs` — history for a run picker (optional) |

Reuses the hardened `do_GET`/`do_POST` handlers (`SourceError` → 500, bad body → 400, bad
`Content-Length` → 400).

## UI (same page, vanilla JS, no deps)

Top toggle `[ Annotate | Results ]`; Annotate view is the existing table, untouched.

Results view — four states:
1. **Empty** (no run): "Finalize & run price match on confirmed stores" + one-line explainer.
2. **Preview** (on click): `GET /api/run/preview` → inline confirm *"Will check P products
   across M sellers (~K ScraperAPI calls, paid). [Run] [Cancel]."*
3. **Running:** progress bar `done / total`, poll `/api/run/status`, re-run disabled.
4. **Table** (loads latest run on open; replaces the progress panel when a run finishes):
   - columns: Naar ₹ · marketplace ₹ · **Δ** (green cheaper / red pricier) · status chip ·
     confirmed seller · competitors (`other_sellers`) · listing
   - filter chips by status + seller search; server paginates (reuse the existing pager)
   - **Download CSV** · run-timestamp header · **Re-run**

On opening Results: `GET /api/results` renders the table if a run exists; `GET /api/run/status`
shows progress if one is mid-flight. Reuses `esc()`, the status chips, and the pagination
controls verbatim.

## Error handling

- **No confirmed stores** → preview `pairs=0` → "confirm some stores first"; no run.
- **Mid-run network failure** → per-pair isolation keeps partial `SOURCE_ERROR` rows; a fatal
  (catalogue fetch dies) → `_job.status=error` + message, and the **last good run stays**.
- **Double-run** → `POST /api/run` → **409** while a job is live.
- **SQLite** → WAL + short busy-timeout; a corrupt/locked DB → **500 JSON**, never a crash.
- **Bad query params** → clamp/ignore; **export with no run** → 404.
- **`api_calls_est`** is a labeled estimate, not a promise.

## Testing (offline, deterministic, no network)

- `results_store` via `sqlite3 :memory:` — `init_db`, `save_run` round-trip, `query_results`
  filter/sort/paginate, `latest_run`, `list_runs`.
- `confirmed_scan_plan` — fixture registry (confirmed subset) + fixture catalogue → correct
  pair count, **only confirmed pairs**, sane estimate.
- `scan_confirmed` — fixture adapters → deterministic Records, `progress_cb` called `total`
  times, **per-pair isolation** (one raising adapter → error row, the rest fine).
- Folded into `poc/naar_price_poc.py --self-test` (engine) + a small `results_store` self-check.

## Files

- **modify** `poc/naar_price_poc.py` — add `confirmed_scan_plan`, `scan_confirmed`, self-tests.
- **create** `poc/results_store.py` — stdlib `sqlite3` results store (+ self-check).
- **modify** `poc/verify_app.py` — job state, 6 endpoints, the `[Annotate|Results]` toggle and
  Results view.
- **data** `poc/results.db` — created at runtime; add to `poc/.gitignore`.
- **docs** `poc/README.md` — a "Results (price-match run)" section.

## Out of scope (YAGNI)

- Scoped/subset runs, per-seller run buttons, auto-run on full annotation (chose all-confirmed
  + preview).
- Postgres / app integration; multi-user; auth.
- Streaming per-row results (poll `done/total` is enough); live re-sort while running.
