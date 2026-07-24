# Annotation → Results View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Results view to the Naar store-verification tool — after annotating (confirming) stores, run a live store-first price-match over the confirmed stores with a cost preview and progress, then show/persist/export the results.

**Architecture:** Extend `poc/verify_app.py` in place with an `[Annotate | Results]` toggle and background-job endpoints; add two testable engine functions (`confirmed_scan_plan`, `scan_confirmed`) to `poc/naar_price_poc.py` reusing the existing `compare_variant`; store results in a new stdlib-`sqlite3` module `poc/results_store.py`. Annotations stay in `seller_identity.json`.

**Tech Stack:** Python 3.11 stdlib only (`sqlite3`, `http.server`, `threading`, `concurrent.futures`, `dataclasses`); vanilla JS front-end (no deps); `requests` for live fetch (already a dep).

## Global Constraints

- **Stdlib-only for new code** — no new pip dependencies (`requests` is the only pre-existing one). SQLite via `import sqlite3`.
- **ESM/imports:** these are Python modules; import the engine as `import naar_price_poc as poc` (verify_app already does `sys.path.insert(0, dirname)` then `import naar_price_poc as poc`).
- **No secrets committed:** `poc/.env`, `poc/seller_identity.json` are gitignored; add `poc/results.db*` too. Never stage them.
- **No `Co-Authored-By: Claude` trailer** in commits; no "Generated with Claude Code" line.
- **Test harness:** the POC has no pytest. Engine tests are `check(label, cond)` calls inside `_test_*(check)` groups run by `python poc/naar_price_poc.py --self-test`. `results_store.py` ships its own `python poc/results_store.py --self-test` (assert-based, uses `sqlite3 :memory:`). Both must print a clear pass/fail summary and exit non-zero on failure.
- **Honesty invariant (unchanged):** a price is only ever on a `MATCHED` row; `scan_confirmed` must not weaken this — it only orchestrates existing `compare_variant`.
- **Record is the source of truth for result columns.** The SQLite `result` table columns == `dataclasses.fields(Record)` names, guarded by a test (Task 3, Step "drift guard").

---

## File Structure

- **Create** `poc/results_store.py` — SQLite results store. Sole responsibility: persist and query runs + result rows. Decoupled from the engine (takes/returns plain dicts). Ships `--self-test`.
- **Modify** `poc/naar_price_poc.py` — add `confirmed_scan_plan` (free cost preview) and `scan_confirmed` (the run), plus a `_test_scan(check)` group registered in `self_test()`.
- **Modify** `poc/verify_app.py` — module-level job state + `_catalogue()` cache; new endpoints (`/api/run/preview`, `POST /api/run`, `/api/run/status`, `/api/results`, `/api/results/export.csv`, `/api/runs`); `[Annotate | Results]` toggle + Results view JS.
- **Modify** `poc/.gitignore` — add `results.db` and SQLite sidecars.
- **Modify** `poc/README.md` — a "Results (price-match run)" section.

Task order: results_store (1–2) → engine (3–4) → endpoints (5–6) → UI (7) → gitignore/docs/final verify (8). Each task ends green and committed.

---

### Task 1: `results_store.py` — schema + `save_run` / `latest_run` / `list_runs`

**Files:**
- Create: `poc/results_store.py`
- Test: self-check inside `poc/results_store.py` (run via `python poc/results_store.py --self-test`)

**Interfaces:**
- Produces:
  - `RESULT_COLS: list[str]` — the result-row column names (== `Record` field names).
  - `init_db(path: str | None = None) -> None`
  - `save_run(meta: dict, rows: list[dict], path: str | None = None) -> int` — `meta` keys: `started_at, finished_at, status, total, done, seller_count, product_count, api_calls_est, error`; `rows` are dicts keyed by `RESULT_COLS` (extra keys ignored, missing → NULL). Returns `run_id`.
  - `latest_run(path=None) -> dict | None` — most recent run's meta (incl. `id`).
  - `list_runs(path=None) -> list[dict]` — all runs, newest first.
  - `_db_path(path=None) -> str` — resolves `path` → `$RESULTS_DB` → `poc/results.db`.
  - `_connect(path) -> sqlite3.Connection` — opens with `row_factory=sqlite3.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`.

- [ ] **Step 1: Write the failing self-check**

Create `poc/results_store.py` with ONLY the test harness first (implementation stubs raise), so the check fails:

```python
#!/usr/bin/env python3
"""SQLite results store for the Naar price-match runs (stdlib sqlite3, no deps).
Persists one `run` row per scan plus its `result` rows; supports querying the
latest run's rows with filter/sort/pagination. Annotations live elsewhere
(seller_identity.json); this module only stores generated results."""
import json
import os
import sqlite3

# Result columns == naar_price_poc.Record fields (kept in sync by a drift-guard
# test in naar_price_poc --self-test). Storage is decoupled from the engine:
# callers pass plain dicts (e.g. dataclasses.asdict(record)).
RESULT_COLS = [
    "naar_product_id", "naar_variant_id", "naar_seller_id", "marketplace", "status",
    "naar_selling_price", "naar_product_title", "naar_variant_name", "naar_seller_name",
    "search_query", "currency", "marketplace_selling_price", "marketplace_unit_price",
    "qty_ratio", "marketplace_sold_by", "marketplace_seller_legal_name",
    "marketplace_seller_gstin", "other_sellers", "listing_id", "listing_url", "offer_ref",
    "delivery_charge", "mrp_displayed", "product_match_method", "seller_match_signal",
    "match_evidence", "confidence", "observed_at",
]
```

Then append the self-check at the bottom:

```python
def _self_test() -> int:
    import tempfile
    fails = []
    def check(label, cond):
        print(("  PASS  " if cond else "  FAIL  ") + label)
        if not cond:
            fails.append(label)

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        init_db(path)
        rid = save_run(
            {"started_at": "t0", "finished_at": "t1", "status": "done",
             "total": 2, "done": 2, "seller_count": 1, "product_count": 1,
             "api_calls_est": 3, "error": ""},
            [{"naar_seller_id": "s1", "naar_product_title": "Amla", "marketplace": "amazon_in",
              "status": "MATCHED", "marketplace_selling_price": 99.0},
             {"naar_seller_id": "s1", "naar_product_title": "Amla", "marketplace": "flipkart",
              "status": "SOURCE_ERROR"}],
            path)
        check("save_run returns an int run id", isinstance(rid, int) and rid > 0)
        lr = latest_run(path)
        check("latest_run returns the saved run", lr and lr["id"] == rid and lr["status"] == "done")
        check("latest_run carries counts", lr["total"] == 2 and lr["seller_count"] == 1)
        runs = list_runs(path)
        check("list_runs returns one run", len(runs) == 1 and runs[0]["id"] == rid)
        rid2 = save_run({"started_at": "t2", "finished_at": "t3", "status": "done",
                         "total": 0, "done": 0, "seller_count": 0, "product_count": 0,
                         "api_calls_est": 0, "error": ""}, [], path)
        check("second run is the latest", latest_run(path)["id"] == rid2)
        check("list_runs newest first", [r["id"] for r in list_runs(path)] == [rid2, rid])
        check("empty db -> latest_run None", latest_run(path + ".empty") is None)
    finally:
        for p in (path, path + "-wal", path + "-shm", path + ".empty"):
            try:
                os.remove(p)
            except OSError:
                pass
    print(f"\n{len(fails)} failure(s)" if fails else "\nAll checks passed.")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_self_test())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python poc/results_store.py --self-test`
Expected: FAIL / traceback — `init_db` / `save_run` not defined.

- [ ] **Step 3: Implement schema + writers**

Insert above `_self_test` (after `RESULT_COLS`):

```python
def _db_path(path=None) -> str:
    if path:
        return path
    env = os.environ.get("RESULTS_DB", "").strip()
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.db")


def _connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path=None) -> None:
    cols = ",\n  ".join(f'"{c}"' for c in RESULT_COLS)
    with _connect(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS run(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT, finished_at TEXT, status TEXT,
            total INTEGER, done INTEGER, seller_count INTEGER, product_count INTEGER,
            api_calls_est INTEGER, error TEXT)""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS result(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES run(id),
            {cols})""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_result_run ON result(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_result_status ON result(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_result_seller ON result(naar_seller_id)")


_RUN_FIELDS = ["started_at", "finished_at", "status", "total", "done",
               "seller_count", "product_count", "api_calls_est", "error"]


def save_run(meta: dict, rows: list, path=None) -> int:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute(
            f"INSERT INTO run({','.join(_RUN_FIELDS)}) VALUES ({','.join('?' * len(_RUN_FIELDS))})",
            [meta.get(k) for k in _RUN_FIELDS])
        run_id = cur.lastrowid
        placeholders = ",".join("?" * (len(RESULT_COLS) + 1))
        colnames = ",".join(["run_id"] + [f'"{c}"' for c in RESULT_COLS])
        conn.executemany(
            f"INSERT INTO result({colnames}) VALUES ({placeholders})",
            [[run_id] + [_cell(r.get(c)) for c in RESULT_COLS] for r in rows])
    return run_id


def _cell(v):
    # sqlite3 stores str/int/float/None natively; anything else -> JSON string.
    if v is None or isinstance(v, (str, int, float)):
        return v
    return json.dumps(v, ensure_ascii=False)


def latest_run(path=None) -> dict:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM run ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def list_runs(path=None) -> list:
    init_db(path)
    with _connect(path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM run ORDER BY id DESC")]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python poc/results_store.py --self-test`
Expected: PASS — "All checks passed." exit 0.

- [ ] **Step 5: Commit**

```bash
git add poc/results_store.py
git commit -m "feat(poc): SQLite results store — schema + save_run/latest_run/list_runs"
```

---

### Task 2: `results_store.py` — `query_results` (filter / sort / paginate)

**Files:**
- Modify: `poc/results_store.py`
- Test: extend `_self_test` in `poc/results_store.py`

**Interfaces:**
- Produces:
  - `query_results(run_id=None, status=None, seller=None, order="matches_first", limit=50, offset=0, path=None) -> tuple[list[dict], int]` — returns `(rows, total_matching)`. `run_id=None` → the latest run. `status` filters exact status. `seller` is a case-insensitive substring on `naar_seller_name`/`naar_seller_id`. `order`: `"matches_first"` (MATCHED first, then by |Δ| desc) or `"delta"` (by Δ desc) or `"seller"`.
- Consumes: Task 1's `_connect`, `latest_run`, `RESULT_COLS`.

- [ ] **Step 1: Write the failing checks**

Append inside `_self_test`, before the `print(...)` summary (reuse the `path`/`rid` from Task 1's harness — add richer rows first). Replace the two-row `save_run` from Task 1 with this richer fixture at the top of the `try` block:

```python
        init_db(path)
        rid = save_run(
            {"started_at": "t0", "finished_at": "t1", "status": "done", "total": 4, "done": 4,
             "seller_count": 2, "product_count": 3, "api_calls_est": 6, "error": ""},
            [{"naar_seller_id": "s1", "naar_seller_name": "Alpha", "naar_product_title": "A",
              "marketplace": "amazon_in", "status": "MATCHED",
              "naar_selling_price": 100.0, "marketplace_unit_price": 130.0},   # Δ +30
             {"naar_seller_id": "s1", "naar_seller_name": "Alpha", "naar_product_title": "B",
              "marketplace": "amazon_in", "status": "MATCHED",
              "naar_selling_price": 100.0, "marketplace_unit_price": 60.0},    # Δ -40 (bigger |Δ|)
             {"naar_seller_id": "s2", "naar_seller_name": "Beta", "naar_product_title": "C",
              "marketplace": "amazon_in", "status": "PRODUCT_NOT_FOUND"},
             {"naar_seller_id": "s2", "naar_seller_name": "Beta", "naar_product_title": "D",
              "marketplace": "flipkart", "status": "SOURCE_ERROR"}],
            path)
```

Then add these checks (after the existing Task-1 checks):

```python
        rows, total = query_results(status="MATCHED", path=path)
        check("query filters by status", total == 2 and all(r["status"] == "MATCHED" for r in rows))
        rows, _ = query_results(order="matches_first", path=path)
        check("matches_first puts MATCHED before others", rows[0]["status"] == "MATCHED")
        check("matches_first orders MATCHED by |delta| desc (B before A)",
              [r["naar_product_title"] for r in rows if r["status"] == "MATCHED"] == ["B", "A"])
        rows, total = query_results(seller="beta", path=path)
        check("query filters by seller substring (case-insensitive)",
              total == 2 and all(r["naar_seller_id"] == "s2" for r in rows))
        rows, total = query_results(limit=1, offset=0, path=path)
        check("pagination returns limit rows but full total", len(rows) == 1 and total == 4)
        rows2, _ = query_results(limit=1, offset=1, path=path)
        check("pagination offset advances", rows2 and rows2[0] != rows[0])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python poc/results_store.py --self-test`
Expected: FAIL — `query_results` not defined.

- [ ] **Step 3: Implement `query_results`**

Insert after `list_runs`:

```python
def query_results(run_id=None, status=None, seller=None, order="matches_first",
                  limit=50, offset=0, path=None):
    init_db(path)
    if run_id is None:
        lr = latest_run(path)
        if not lr:
            return [], 0
        run_id = lr["id"]
    where = ["run_id = ?"]
    args = [run_id]
    if status:
        where.append("status = ?")
        args.append(status)
    if seller:
        where.append("(lower(naar_seller_name) LIKE ? OR lower(naar_seller_id) LIKE ?)")
        like = f"%{seller.lower()}%"
        args += [like, like]
    clause = " AND ".join(where)
    # Δ per unit vs Naar: prefer unit price, else selling price.
    delta = ("(COALESCE(marketplace_unit_price, marketplace_selling_price) - naar_selling_price)")
    if order == "delta":
        order_by = f"{delta} DESC"
    elif order == "seller":
        order_by = "lower(naar_seller_name), naar_product_title"
    else:  # matches_first: MATCHED rows first, then largest absolute Δ
        order_by = (f"(status = 'MATCHED') DESC, "
                    f"ABS({delta}) DESC, id ASC")
    with _connect(path) as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM result WHERE {clause}", args).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM result WHERE {clause} ORDER BY {order_by} LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)]).fetchall()
    return [dict(r) for r in rows], total
```

- [ ] **Step 4: Run to verify it passes**

Run: `python poc/results_store.py --self-test`
Expected: PASS — all checks incl. the 6 new query checks.

- [ ] **Step 5: Commit**

```bash
git add poc/results_store.py
git commit -m "feat(poc): results_store query_results — filter/sort/paginate"
```

---

### Task 3: `naar_price_poc.py` — `confirmed_scan_plan` (free cost preview)

**Files:**
- Modify: `poc/naar_price_poc.py` — add `confirmed_scan_plan`; add `_test_scan(check)` and register it in `self_test()`.
- Test: `python poc/naar_price_poc.py --self-test`

**Interfaces:**
- Produces:
  - `confirmed_scan_plan(products: list[dict], marketplaces: list[str]) -> dict` — returns `{"sellers": int, "products": int, "pairs": int, "api_calls_est": int, "plan": list}` where each plan item is `(product, variant, marketplace, store)`. A pair exists only when `store_status(product["sellerId"], marketplace) == "confirmed"`. `store` is `_confirmed_store(sellerId, marketplace)`. NO network — reads registry + given products only.
- Consumes: existing `store_status`, `_confirmed_store`, `iter_variants`, `_to_float`.

- [ ] **Step 1: Write the failing test group**

Add a new group function above `def self_test()` (near the other `_test_*`):

```python
def _test_scan(check):
    """confirmed_scan_plan is free (no network) and expands only CONFIRMED
    (product, variant, marketplace) pairs; scan_confirmed runs them store-first."""
    import tempfile as _tf
    global _seller_identity_cache
    saved = os.environ.get("NAAR_KYC_FILE")
    fd, reg = _tf.mkstemp(suffix=".json")
    os.close(fd)
    os.environ["NAAR_KYC_FILE"] = reg
    _seller_identity_cache = None
    try:
        confirm_store("sa", "amazon_in", seller_display="Alpha Store")
        # products: sa confirmed on amazon_in (1 variant) -> 1 pair; sb unconfirmed -> 0
        products = [
            {"_id": "pa", "title": "Amla", "sellerId": "sa", "seller": {"storeName": "Alpha Store"},
             "variants": [{"_id": "va", "attributes": {"weight": "100g"}, "variantName": "100g",
                           "sellingPrice": 90.0}]},
            {"_id": "pb", "title": "Honey", "sellerId": "sb", "seller": {"storeName": "Beta"},
             "variants": [{"_id": "vb", "attributes": {}, "variantName": "-", "sellingPrice": 50.0}]},
        ]
        plan = confirmed_scan_plan(products, ["amazon_in", "flipkart"])
        check("plan counts only confirmed pairs", plan["pairs"] == 1 and plan["sellers"] == 1)
        check("plan skips unconfirmed sellers",
              all(item[0]["sellerId"] == "sa" for item in plan["plan"]))
        check("plan estimates api calls (>= pairs)", plan["api_calls_est"] >= plan["pairs"])
    finally:
        _seller_identity_cache = None
        os.environ.pop("NAAR_KYC_FILE", None)
        if saved is not None:
            os.environ["NAAR_KYC_FILE"] = saved
        try:
            os.remove(reg)
        except OSError:
            pass

    # drift guard: SQLite result columns must match Record fields exactly
    import results_store as _rs
    check("results_store.RESULT_COLS == Record fields (no schema drift)",
          list(_rs.RESULT_COLS) == [f.name for f in dataclasses.fields(Record)])
```

Register it in `self_test()` after `_test_store_registry(check)`:

```python
    _test_store_registry(check)
    _test_scan(check)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python poc/naar_price_poc.py --self-test`
Expected: FAIL — `confirmed_scan_plan` not defined (and `results_store` import — that module exists from Task 1).

- [ ] **Step 3: Implement `confirmed_scan_plan`**

Add near `run()` (above it):

```python
def confirmed_scan_plan(products: list, marketplaces: list) -> dict:
    """Cost preview for a store-first run — NO network. Expands every
    (product, variant, marketplace) whose seller's store is CONFIRMED on that
    marketplace. `plan` items are (product, variant, marketplace, store)."""
    plan = []
    sellers = set()
    prod_ids = set()
    for product in products:
        sid = str(product.get("sellerId") or "")
        confirmed = [m for m in marketplaces if store_status(sid, m) == "confirmed"]
        if not confirmed:
            continue
        for variant in iter_variants(product):
            if _to_float(variant.get("sellingPrice")) is None:
                continue
            for m in confirmed:
                store = _confirmed_store(sid, m)
                if store is None:
                    continue
                plan.append((product, variant, m, store))
                sellers.add(sid)
                prod_ids.add(product.get("_id", ""))
    # each pair ~ 1 search + up to 5 product fetches (AmazonInAdapter caps at 5)
    return {"sellers": len(sellers), "products": len(prod_ids), "pairs": len(plan),
            "api_calls_est": len(plan) * 6, "plan": plan}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python poc/naar_price_poc.py --self-test`
Expected: PASS — the 4 new scan/drift checks green, plus all prior checks.

- [ ] **Step 5: Commit**

```bash
git add poc/naar_price_poc.py
git commit -m "feat(poc): confirmed_scan_plan — free store-first cost preview"
```

---

### Task 4: `naar_price_poc.py` — `scan_confirmed` (the run, with progress + isolation)

**Files:**
- Modify: `poc/naar_price_poc.py` — add `scan_confirmed`; extend `_test_scan`.
- Test: `python poc/naar_price_poc.py --self-test`

**Interfaces:**
- Produces:
  - `scan_confirmed(plan: list, adapters: dict, progress_cb=None, llm_judge=False, strict=False) -> list[Record]` — iterates `plan` items `(product, variant, marketplace, store)`, calls `compare_variant(product, variant, adapters[marketplace], llm_judge, strict, store=store)`, appends the `Record`, and calls `progress_cb(done, total)` after each. Per-item `try/except` — a raising item yields a `SOURCE_ERROR` Record, never aborts.
- Consumes: existing `compare_variant`, `Record`, `SourceError`; Task 3's plan shape.

- [ ] **Step 1: Write the failing checks**

Append inside `_test_scan` (before the `finally`, after the plan checks, still inside `try`):

```python
        # scan_confirmed runs the plan store-first, with progress + isolation
        class _Ok(MarketplaceAdapter):
            name = "amazon_in"
            def search(self, q):
                return [Candidate("amazon_in", "L", "u", "Amla Powder 100g",
                                  [Offer("Alpha Store", price_inr=130.0)])]
        class _Boom(MarketplaceAdapter):
            name = "amazon_in"
            def search(self, q):
                raise RuntimeError("kaboom")   # NOT SourceError -> tests isolation
        prod = products[0]
        var = prod["variants"][0]
        store = _confirmed_store("sa", "amazon_in")
        seen = []
        recs = scan_confirmed([(prod, var, "amazon_in", store)], {"amazon_in": _Ok()},
                              progress_cb=lambda d, t: seen.append((d, t)))
        check("scan_confirmed MATCHES via the confirmed store",
              len(recs) == 1 and recs[0].status == "MATCHED"
              and recs[0].marketplace_sold_by == "Alpha Store")
        check("progress_cb called once per pair with (done,total)", seen == [(1, 1)])
        recs2 = scan_confirmed([(prod, var, "amazon_in", store)], {"amazon_in": _Boom()})
        check("scan_confirmed isolates a raising pair -> SOURCE_ERROR row (no abort)",
              len(recs2) == 1 and recs2[0].status == "SOURCE_ERROR")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python poc/naar_price_poc.py --self-test`
Expected: FAIL — `scan_confirmed` not defined.

- [ ] **Step 3: Implement `scan_confirmed`**

Add directly below `confirmed_scan_plan`:

```python
def scan_confirmed(plan: list, adapters: dict, progress_cb=None,
                   llm_judge: bool = False, strict: bool = False) -> list:
    """Run a store-first price match over a confirmed-pairs plan (from
    confirmed_scan_plan). Each item is (product, variant, marketplace, store).
    Per-item isolation: one failure becomes a SOURCE_ERROR row, never aborts.
    Calls progress_cb(done, total) after each item."""
    total = len(plan)
    records = []
    for i, (product, variant, marketplace, store) in enumerate(plan):
        try:
            rec = compare_variant(product, variant, adapters[marketplace],
                                  llm_judge, strict, store=store)
        except Exception as e:   # defence in depth (compare_variant already guards)
            rec = Record(product.get("_id", ""), variant.get("_id", ""),
                         product.get("sellerId", ""), marketplace, "SOURCE_ERROR",
                         match_evidence=f"{type(e).__name__}: {e}")
        records.append(rec)
        if progress_cb:
            progress_cb(i + 1, total)
    return records
```

- [ ] **Step 4: Run to verify it passes**

Run: `python poc/naar_price_poc.py --self-test`
Expected: PASS — the 3 new scan_confirmed checks + all prior.

- [ ] **Step 5: Commit**

```bash
git add poc/naar_price_poc.py
git commit -m "feat(poc): scan_confirmed — store-first run with progress + per-pair isolation"
```

---

### Task 5: `verify_app.py` — background job + run endpoints

**Files:**
- Modify: `poc/verify_app.py` — add `_catalogue()` cache, job state, `warm`/thread helpers, and `do_GET`/`do_POST` routes for `/api/run/preview`, `POST /api/run`, `/api/run/status`.
- Test: manual (server) — commands below.

**Interfaces:**
- Consumes: `poc.confirmed_scan_plan`, `poc.scan_confirmed`, `poc._all_naar_products`, `poc.AmazonInAdapter`/`_adapter`, `results_store.save_run`, `poc._now_iso`.
- Produces (module-level, for Task 6/7):
  - `_job: dict` with keys `status` (`idle|running|done|error`), `done`, `total`, `run_id`, `started`, `error`; guarded by `_job_lock`.
  - `_catalogue() -> list` — cached full product list (`poc._all_naar_products()`), fixture list under `--fixture`.
  - `MARKETPLACES` already exists.

- [ ] **Step 1: Add job state + catalogue cache**

Near the top of `verify_app.py`, after `_sellers_error = ""` line, add:

```python
import results_store
_products_cache: list = []
_job = {"status": "idle", "done": 0, "total": 0, "run_id": None, "started": "", "error": ""}
_job_lock = threading.Lock()
```

Add helper functions near `load_naar_sellers`:

```python
def _catalogue() -> list:
    """Full product list for a run (cached). Fixture list offline; live catalogue otherwise."""
    global _products_cache
    if _products_cache:
        return _products_cache
    _products_cache = list(poc.FIXTURE_NAAR) if USE_FIXTURE else _all_naar_products()
    return _products_cache


def _adapters() -> dict:
    return {m: _adapter(m) for m in MARKETPLACES}


def _run_scan_job(plan) -> None:
    """Background worker: run the plan, persist to SQLite, update _job."""
    try:
        def progress(done, total):
            with _job_lock:
                _job["done"], _job["total"] = done, total
        records = poc.scan_confirmed(plan, _adapters(), progress_cb=progress)
        rows = [__import__("dataclasses").asdict(r) for r in records]
        n_sellers = len({r.get("naar_seller_id") for r in rows})
        n_products = len({r.get("naar_product_id") for r in rows})
        rid = results_store.save_run(
            {"started_at": _job["started"], "finished_at": poc._now_iso(), "status": "done",
             "total": len(plan), "done": len(plan), "seller_count": n_sellers,
             "product_count": n_products, "api_calls_est": len(plan) * 6, "error": ""},
            rows)
        with _job_lock:
            _job.update(status="done", run_id=rid, done=len(plan), total=len(plan))
    except Exception as e:                    # never leave the job stuck on "running"
        with _job_lock:
            _job.update(status="error", error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Add the routes**

In `do_GET`, inside the `try:` block (with the other `/api/*` routes), add:

```python
            if u.path == "/api/run/preview":
                plan = poc.confirmed_scan_plan(_catalogue(), list(MARKETPLACES))
                return self._send(200, json.dumps({k: plan[k] for k in
                    ("sellers", "products", "pairs", "api_calls_est")}))
            if u.path == "/api/run/status":
                with _job_lock:
                    return self._send(200, json.dumps(dict(_job)))
```

In `do_POST`, after the `isinstance(body, dict)` guard and inside the `try:` block, add (before the `/api/confirm` route is fine):

```python
            if u.path == "/api/run":
                with _job_lock:
                    if _job["status"] == "running":
                        return self._send(409, json.dumps({"error": "a run is already in progress"}))
                    _job.update(status="running", done=0, total=0, run_id=None,
                                started=poc._now_iso(), error="")
                plan = poc.confirmed_scan_plan(_catalogue(), list(MARKETPLACES))
                with _job_lock:
                    _job["total"] = len(plan["plan"])
                if not plan["plan"]:
                    with _job_lock:
                        _job.update(status="error", error="no confirmed stores to run")
                    return self._send(400, json.dumps({"error": "no confirmed stores to run"}))
                threading.Thread(target=_run_scan_job, args=(plan["plan"],), daemon=True).start()
                return self._send(200, json.dumps({"started": True, "total": len(plan["plan"])}))
```

- [ ] **Step 3: Manual verify — preview + run + status (fixture)**

Run the server against fixture on a scratch registry + a scratch db, with the fixture seller pre-confirmed:

```bash
cd /path/to/Naar-Price-Match
SCRATCH=$(mktemp -d)
NAAR_KYC_FILE=$SCRATCH/reg.json RESULTS_DB=$SCRATCH/results.db VERIFY_PORT=8799 \
  python -u poc/verify_app.py --fixture &
sleep 2
# confirm the fixture seller's amazon store so a pair exists
curl -s -XPOST localhost:8799/api/confirm \
  -d '{"seller_id":"ns_treasure","marketplace":"amazon_in","seller_display":"TREASURE FLAVOURS"}'
curl -s localhost:8799/api/run/preview            # expect pairs >= 1
curl -s -XPOST localhost:8799/api/run -d '{}'     # expect {"started":true,...}
sleep 3
curl -s localhost:8799/api/run/status             # expect status done, run_id set
```

Expected: preview shows `pairs` ≥ 1; POST returns `started:true`; status ends `"status":"done"` with a `run_id`. (Fixture adapter needs no network.)

- [ ] **Step 4: Kill the server**

```bash
pkill -f verify_app.py
```

- [ ] **Step 5: Commit**

```bash
git add poc/verify_app.py
git commit -m "feat(poc): verify_app run endpoints — preview/run/status + background job"
```

---

### Task 6: `verify_app.py` — results + export endpoints

**Files:**
- Modify: `poc/verify_app.py` — add `/api/results`, `/api/results/export.csv`, `/api/runs` to `do_GET`.
- Test: manual (continue from Task 5's server).

**Interfaces:**
- Consumes: `results_store.query_results`, `results_store.latest_run`, `results_store.list_runs`.
- Produces: JSON `{rows, total, run}` for the table; a CSV stream for download.

- [ ] **Step 1: Add the routes**

In `do_GET`, inside the `try:` block, add:

```python
            if u.path == "/api/results":
                q = parse_qs(u.query)
                def _q(name, default=""):
                    return (q.get(name) or [default])[0]
                run_id = _q("run_id")
                rows, total = results_store.query_results(
                    run_id=int(run_id) if run_id.isdigit() else None,
                    status=_q("status") or None, seller=_q("seller") or None,
                    order=_q("order", "matches_first"),
                    limit=int(_q("limit", "50") or 50), offset=int(_q("offset", "0") or 0))
                return self._send(200, json.dumps(
                    {"rows": rows, "total": total, "run": results_store.latest_run()}))
            if u.path == "/api/runs":
                return self._send(200, json.dumps(results_store.list_runs()))
            if u.path == "/api/results/export.csv":
                import csv as _csv
                import io as _io
                q = parse_qs(u.query)
                run_id = (q.get("run_id") or [""])[0]
                rows, _ = results_store.query_results(
                    run_id=int(run_id) if run_id.isdigit() else None, limit=100000)
                buf = _io.StringIO()
                w = _csv.DictWriter(buf, fieldnames=results_store.RESULT_COLS, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow(r)
                data = buf.getvalue().encode("utf-8-sig")
                self.send_response(200)
                self.send_header("content-type", "text/csv; charset=utf-8")
                self.send_header("content-disposition", 'attachment; filename="naar_price_match.csv"')
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
```

- [ ] **Step 2: Manual verify — results + export**

Continue from Task 5's server (or relaunch + re-confirm + run, then):

```bash
curl -s "localhost:8799/api/results?status=&limit=5" | python3 -m json.tool | head -20
curl -s "localhost:8799/api/results/export.csv" -o /tmp/out.csv && head -1 /tmp/out.csv && wc -l /tmp/out.csv
```

Expected: `/api/results` returns `{"rows":[...],"total":N,"run":{...}}`; `export.csv` downloads a CSV whose header is the `RESULT_COLS` and has ≥1 data row (fixture MATCHED).

- [ ] **Step 3: Kill server**

```bash
pkill -f verify_app.py
```

- [ ] **Step 4: Commit**

```bash
git add poc/verify_app.py
git commit -m "feat(poc): verify_app results + CSV export endpoints"
```

---

### Task 7: `verify_app.py` — `[Annotate | Results]` UI

**Files:**
- Modify: `poc/verify_app.py` — the `PAGE` HTML/JS: add the toggle, a `#results` section, and its JS (preview → run → progress → table → export).
- Test: manual (browser or curl of `/` for presence; behaviour via the endpoints above).

**Interfaces:**
- Consumes: `/api/run/preview`, `/api/run` (POST), `/api/run/status`, `/api/results`, `/api/results/export.csv`.
- Produces: user-visible Results view. Reuses existing `j()`, `esc()`, `stChip()`.

- [ ] **Step 1: Add the toggle + results container to the HTML**

In `PAGE`, immediately after the `<h1>…</h1>` line, add:

```html
<div id=tabs style="margin:8px 0">
  <button id=tab_annotate class=primary>Annotate</button>
  <button id=tab_results>Results</button>
</div>
```

Wrap the existing controls + table (the `#bar` div and `#t` table) in a section:

```html
<div id=view_annotate>
  <!-- existing #bar and #t table stay here, unchanged -->
</div>
<div id=view_results style="display:none">
  <div id=run_panel style="margin:10px 0"></div>
  <div id=res_bar style="display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap">
    <input type=text id=rq placeholder="filter by seller" style="width:240px">
    <select id=rstatus>
      <option value="">all statuses</option>
      <option>MATCHED</option><option>PRODUCT_NOT_FOUND</option>
      <option>OUT_OF_STOCK</option><option>SOURCE_ERROR</option>
    </select>
    <a id=dlcsv href="/api/results/export.csv"><button>Download CSV</button></a>
    <span style="flex:1"></span>
    <button id=rprev>‹ Prev</button><span id=rpg class=muted>0</span><button id=rnext>Next ›</button>
  </div>
  <table id=rt><thead><tr>
    <th>Seller</th><th>Product</th><th>Market</th><th>Naar ₹</th><th>Mkt ₹</th>
    <th>Δ</th><th>Status</th><th>Sold by</th><th>Also sold by</th>
  </tr></thead><tbody></tbody></table>
</div>
```

- [ ] **Step 2: Add the Results JS**

Just before the final `load();` line in the `<script>`, add:

```javascript
// --- view toggle ---
function showView(v){
  document.getElementById('view_annotate').style.display = v==='annotate'?'':'none';
  document.getElementById('view_results').style.display  = v==='results'?'':'none';
  document.getElementById('tab_annotate').className = v==='annotate'?'primary':'';
  document.getElementById('tab_results').className  = v==='results'?'primary':'';
  if(v==='results') resultsInit();
}
document.getElementById('tab_annotate').onclick=()=>showView('annotate');
document.getElementById('tab_results').onclick=()=>showView('results');

// --- results state ---
let RPAGE=0, RPSIZE=25, RQ='', RSTATUS='';
let _pollTimer=null;

async function resultsInit(){
  const st=await j('/api/run/status');
  if(st.status==='running'){ renderRunning(st); pollRun(); }
  else { renderRunPanel(st); loadResults(); }
}
function renderRunPanel(st){
  const p=document.getElementById('run_panel');
  const note = st.status==='error' ? `<span class=muted>last run error: ${esc(st.error)}</span>` : '';
  p.innerHTML=`<button id=runbtn class=primary>Finalize &amp; run price match</button> ${note}`;
  document.getElementById('runbtn').onclick=previewRun;
}
async function previewRun(){
  const pv=await j('/api/run/preview');
  const p=document.getElementById('run_panel');
  p.innerHTML=`<div class=cands>Will check <b>${pv.products}</b> products across
    <b>${pv.sellers}</b> confirmed sellers (~<b>${pv.api_calls_est}</b> ScraperAPI calls, paid).
    <button id=go class=primary>Run</button> <button id=cancel>Cancel</button></div>`;
  document.getElementById('cancel').onclick=()=>renderRunPanel({status:'idle'});
  document.getElementById('go').onclick=async()=>{
    const r=await j('/api/run',{method:'POST',body:'{}'});
    if(r&&r.error){ p.innerHTML=`<span class=muted>${esc(r.error)}</span>`; renderRunPanel({status:'idle'}); return; }
    pollRun();
  };
}
function renderRunning(st){
  document.getElementById('run_panel').innerHTML=
    `<div class=cands>running price match… <b>${st.done}</b> / <b>${st.total||'?'}</b></div>`;
}
function pollRun(){
  clearTimeout(_pollTimer);
  _pollTimer=setTimeout(async()=>{
    const st=await j('/api/run/status');
    if(st.status==='running'){ renderRunning(st); pollRun(); }
    else { renderRunPanel(st); loadResults(); }
  },1500);
}
async function loadResults(){
  const url=`/api/results?status=${encodeURIComponent(RSTATUS)}&seller=${encodeURIComponent(RQ)}`
    +`&limit=${RPSIZE}&offset=${RPAGE*RPSIZE}`;
  const d=await j(url);
  const tb=document.querySelector('#rt tbody'); tb.innerHTML='';
  document.getElementById('dlcsv').href='/api/results/export.csv';
  const rows=d.rows||[];
  if(!rows.length){ tb.innerHTML='<tr><td colspan=9 class=muted>no results yet — run a price match</td></tr>'; }
  for(const r of rows){
    const naar=r.naar_selling_price, mkt=(r.marketplace_unit_price!=null?r.marketplace_unit_price:r.marketplace_selling_price);
    const delta=(naar!=null&&mkt!=null)?(mkt-naar):null;
    const dtxt=delta==null?'':(delta>=0?`+${delta.toFixed(2)}`:delta.toFixed(2));
    const dcol=delta==null?'':(delta<0?'#0a0':'#a00');
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${esc(r.naar_seller_name||r.naar_seller_id)}</td>
      <td>${esc(r.naar_product_title)} <span class=muted>${esc(r.naar_variant_name||'')}</span></td>
      <td>${esc(r.marketplace)}</td>
      <td>${naar!=null?naar.toFixed(2):''}</td>
      <td>${mkt!=null?mkt.toFixed(2):''}</td>
      <td style="color:${dcol}">${dtxt}</td>
      <td>${stChip((r.status||'').toLowerCase().slice(0,4))}${esc(r.status)}</td>
      <td>${esc(r.marketplace_sold_by||'')}</td>
      <td class=muted>${esc((r.other_sellers||'').slice(0,60))}</td>`;
    tb.appendChild(tr);
  }
  const total=d.total||0, start=RPAGE*RPSIZE;
  document.getElementById('rpg').textContent= total?`${start+1}–${Math.min(start+RPSIZE,total)} of ${total}`:'0';
  document.getElementById('rprev').disabled= RPAGE<=0;
  document.getElementById('rnext').disabled= start+RPSIZE>=total;
}
document.getElementById('rq').oninput=e=>{RQ=e.target.value;RPAGE=0;loadResults();};
document.getElementById('rstatus').onchange=e=>{RSTATUS=e.target.value;RPAGE=0;loadResults();};
document.getElementById('rprev').onclick=()=>{if(RPAGE>0){RPAGE--;loadResults();}};
document.getElementById('rnext').onclick=()=>{RPAGE++;loadResults();};
```

Note: the `stChip` call passes a short status class; the existing `.st` CSS colours `confirmed/rejected/pending` only, so status text is shown alongside — acceptable (no new CSS needed). Leave a plain text status if preferred.

- [ ] **Step 3: Manual verify — page renders both views**

```bash
curl -s localhost:8799/ | grep -c "view_results"     # expect 1
curl -s localhost:8799/ | grep -c "Finalize"         # button text present via JS -> 0 in static HTML is OK
```

Then in a browser: open `localhost:8799`, click **Results**, click **Finalize & run**, confirm the preview count, **Run**, watch progress, see the table + **Download CSV**. (Use the fixture server with a confirmed seller.)

- [ ] **Step 4: JS syntax check (node, if available)**

```bash
python3 - <<'PY'
import re,pathlib,subprocess,tempfile,os,shutil
if not shutil.which("node"): print("node absent — skip"); raise SystemExit
js=re.search(r"<script>(.*?)</script>",pathlib.Path("poc/verify_app.py").read_text(),re.S).group(1)
f=tempfile.NamedTemporaryFile("w",suffix=".js",delete=False);f.write(js);f.close()
print("JS:", "OK" if subprocess.run(["node","--check",f.name]).returncode==0 else "FAIL"); os.unlink(f.name)
PY
```

Expected: `JS: OK`.

- [ ] **Step 5: Commit**

```bash
git add poc/verify_app.py
git commit -m "feat(poc): verify_app Annotate|Results toggle + results view"
```

---

### Task 8: gitignore + docs + full-suite verification

**Files:**
- Modify: `poc/.gitignore` — ignore the results DB.
- Modify: `poc/README.md` — add a "Results (price-match run)" subsection.
- Test: run the whole offline suite.

- [ ] **Step 1: Ignore the results DB**

Append to `poc/.gitignore`:

```
results.db
results.db-wal
results.db-shm
```

- [ ] **Step 2: Document the Results flow**

Add to `poc/README.md`, after the store-verification section:

```markdown
### Results (price-match run)

In `verify_app.py`, switch to the **Results** tab. **Finalize & run** shows a cost
preview (products × confirmed sellers × ~calls), then runs a store-first price
match over the **confirmed** stores in the background (progress bar). Results are
stored in `poc/results.db` (SQLite, gitignored) and persist across restarts; the
table filters by status/seller and **Download CSV** exports the shareable sheet.
Storage: `results_store.py`. Engine: `confirmed_scan_plan` (free preview) +
`scan_confirmed` (the run) in `naar_price_poc.py`.
```

- [ ] **Step 3: Run the whole offline suite**

```bash
python poc/results_store.py --self-test && \
python poc/naar_price_poc.py --self-test && \
python poc/eval_accuracy.py && \
python poc/prove_llm.py && \
python -m py_compile poc/*.py && echo "ALL GREEN"
```

Expected: every step passes; ends `ALL GREEN`.

- [ ] **Step 4: Commit**

```bash
git add poc/.gitignore poc/README.md
git commit -m "chore(poc): ignore results.db; document the Results run flow"
```

---

## Self-Review

**Spec coverage:**
- Flow annotate→finalize→results — Tasks 5–7 (toggle, preview, run, table). ✓
- UI runs scan live w/ progress — Task 5 (`_run_scan_job`, status) + Task 7 (poll). ✓
- Run all confirmed + cost preview — Task 3 (`confirmed_scan_plan`) + Task 5/7 (preview UI). ✓
- Filterable results table — Task 2 (`query_results`) + Task 6 (endpoint) + Task 7 (table/filters/pager). ✓
- Persist + CSV export — Task 1 (`save_run`) + Task 6 (`export.csv`). ✓
- SQLite results, JSON annotations untouched — Tasks 1–2; annotations code not modified. ✓
- Error handling (no-confirmed→400, double-run→409, job-error captured, isolation) — Tasks 4/5. ✓
- Testing (results_store `:memory:`, plan/scan checks, drift guard) — Tasks 1–4. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test step shows asserts + expected output. ✓

**Type consistency:** `confirmed_scan_plan` returns `{sellers,products,pairs,api_calls_est,plan}`; `plan` items `(product,variant,marketplace,store)` consumed identically by `scan_confirmed` and `_run_scan_job`. `save_run(meta, rows)` / `query_results(...)-> (rows,total)` used consistently in Tasks 5–6. `RESULT_COLS` shared by store + export + drift guard. ✓

**Note on ordering:** Task 3's `_test_scan` imports `results_store` — it exists from Task 1, so run tasks in order. If executed out of order, Task 3's drift-guard check fails until Task 1 lands.
