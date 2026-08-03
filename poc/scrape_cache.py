#!/usr/bin/env python3
"""Disposable SQLite cache for ScraperAPI structured responses (stdlib only).
Repeat discovery/scan of the same product is served from here — no credit, no
wait. Cache key never contains the api_key (the params passed in are clean). Only
successful dict responses are stored; a cache-layer error never breaks a fetch."""
import hashlib
import json
import os
import sqlite3
import time


def enabled() -> bool:
    return os.environ.get("SCRAPE_CACHE", "on") != "off"


def ttl() -> int:
    try:
        return int(os.environ.get("SCRAPE_CACHE_TTL", "604800"))
    except ValueError:
        return 604800


def _db_path(path=None) -> str:
    if path:
        return path
    env = os.environ.get("SCRAPE_CACHE_DB", "").strip()
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrape_cache.db")


def _connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""CREATE TABLE IF NOT EXISTS cache(
        key TEXT PRIMARY KEY, kind TEXT, params TEXT, body TEXT, fetched_at INTEGER)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_cache_fetched ON cache(fetched_at)")
    return conn


def cache_key(kind: str, params: dict) -> str:
    raw = kind + "\n" + json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(kind: str, params: dict, ttl_seconds: int, path=None):
    if ttl_seconds is None or ttl_seconds <= 0:
        return None
    try:
        with _connect(path) as conn:
            row = conn.execute("SELECT body, fetched_at FROM cache WHERE key = ?",
                               (cache_key(kind, params),)).fetchone()
    except (sqlite3.Error, OSError, TypeError):
        return None                       # cache is an optimization, never a failure
    if not row:
        return None
    if time.time() - row["fetched_at"] >= ttl_seconds:
        return None
    try:
        return json.loads(row["body"])
    except (ValueError, TypeError):
        return None


def put(kind: str, params: dict, body: dict, path=None, ts=None) -> None:
    try:
        with _connect(path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache(key, kind, params, body, fetched_at) VALUES (?,?,?,?,?)",
                (cache_key(kind, params), kind,
                 json.dumps(params, sort_keys=True, ensure_ascii=False),
                 json.dumps(body, ensure_ascii=False),
                 int(ts if ts is not None else time.time())))
    except (sqlite3.Error, OSError, TypeError):
        return                            # never break a fetch on a cache write


def prune(ttl_seconds: int, path=None) -> int:
    try:
        with _connect(path) as conn:
            cur = conn.execute("DELETE FROM cache WHERE fetched_at < ?",
                               (int(time.time()) - int(ttl_seconds),))
            return cur.rowcount
    except (sqlite3.Error, OSError):
        return 0


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
        body = {"results": [{"asin": "A1", "name": "X"}]}
        put("amazon/search", {"query": "amla"}, body, path=path)
        check("get returns the cached body (fresh)",
              get("amazon/search", {"query": "amla"}, 3600, path=path) == body)
        check("get miss on unknown params",
              get("amazon/search", {"query": "other"}, 3600, path=path) is None)
        check("ttl<=0 is always a miss",
              get("amazon/search", {"query": "amla"}, 0, path=path) is None)
        put("amazon/product", {"asin": "B"}, {"sold_by": "S"}, path=path, ts=time.time() - 10_000)
        check("entry older than ttl -> miss",
              get("amazon/product", {"asin": "B"}, 3600, path=path) is None)
        check("same entry within a large ttl -> hit",
              get("amazon/product", {"asin": "B"}, 1_000_000, path=path) == {"sold_by": "S"})
        k1 = cache_key("amazon/product", {"asin": "B"})
        check("cache_key stable + excludes api_key",
              k1 == cache_key("amazon/product", {"asin": "B"}) and "api_key" not in k1)
        # cache-layer error never raises (unwritable path)
        check("get on a bad db path returns None, no raise",
              get("amazon/search", {"query": "z"}, 10, path="/nonexistent-dir/x/y.db") is None)
        _ok = True
        try:
            put("amazon/search", {"query": "z"}, {"a": 1}, path="/nonexistent-dir/x/y.db")
        except Exception:
            _ok = False
        check("put on a bad db path no-ops, no raise", _ok)
        # env helpers
        os.environ["SCRAPE_CACHE"] = "off"
        check("SCRAPE_CACHE=off -> disabled", enabled() is False)
        os.environ["SCRAPE_CACHE"] = "on"
        os.environ["SCRAPE_CACHE_TTL"] = "123"
        check("SCRAPE_CACHE_TTL honored", enabled() is True and ttl() == 123)
    finally:
        os.environ.pop("SCRAPE_CACHE", None)
        os.environ.pop("SCRAPE_CACHE_TTL", None)
        for p in (path, path + "-wal", path + "-shm"):
            try:
                os.remove(p)
            except OSError:
                pass
    print(f"\n{len(fails)} failure(s)" if fails else "\nAll checks passed.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
