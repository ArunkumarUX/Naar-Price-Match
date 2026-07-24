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
