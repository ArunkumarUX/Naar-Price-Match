# ScraperAPI Response Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cache successful ScraperAPI structured responses in a disposable SQLite DB so repeat store-discovery / price-match runs of the same product are instant and free.

**Architecture:** New stdlib-`sqlite3` module `poc/scrape_cache.py` (get/put/prune + `--self-test`). Wrap the single choke point `_scraperapi_structured` in `poc/naar_price_poc.py`: check cache → fetch on miss → store only successful dict responses. Separate `poc/scrape_cache.db` (gitignored). Single TTL (default 7d), `SCRAPE_CACHE=off` bypass.

**Tech Stack:** Python 3.11 stdlib only (`sqlite3`, `hashlib`, `json`, `time`, `os`).

## Global Constraints

- **Stdlib only** — no new pip deps.
- **Cache key must NEVER contain the api_key.** The `params` arg to `_scraperapi_structured` is already clean (`{"query":…}` / `{"asin":…}`); the api_key is added *inside* the function. Key = `sha256(kind + "\n" + json.dumps(params, sort_keys=True, ensure_ascii=False))`.
- **Only successful dict responses are cached.** Every `SourceError` path (credits, non-JSON, non-dict, HTTP≥400) must raise BEFORE any `put`.
- **The cache never breaks a fetch.** `get`/`put` swallow their own `sqlite3.Error`/`OSError` and fall through to the live path.
- **Env:** `SCRAPE_CACHE` (`on`/`off`, default on), `SCRAPE_CACHE_TTL` (seconds, default `604800`), `SCRAPE_CACHE_DB` (path, default `poc/scrape_cache.db`).
- Test harness: `python poc/scrape_cache.py --self-test` and `python poc/naar_price_poc.py --self-test`. No pytest.
- No `Co-Authored-By: Claude` trailer / "Generated with Claude Code" line in commits.

---

## File Structure

- **create** `poc/scrape_cache.py` — cache module. Sole responsibility: store/fetch raw responses. Decoupled from the engine (plain dicts in/out). Ships `--self-test`.
- **modify** `poc/naar_price_poc.py` — wrap `_scraperapi_structured`; add `_test_scrape_cache(check)` registered in `self_test()`.
- **modify** `poc/.gitignore` — ignore `scrape_cache.db*`.
- **modify** `poc/README.md` — a short "Scrape cache" note.

Task order: module (1) → wrap + engine test (2) → gitignore/docs/verify (3).

---

### Task 1: `scrape_cache.py` — cache module

**Files:**
- Create: `poc/scrape_cache.py`
- Test: self-check via `python poc/scrape_cache.py --self-test`

**Interfaces:**
- Produces: `enabled() -> bool`, `ttl() -> int`, `cache_key(kind, params) -> str`,
  `get(kind, params, ttl, path=None) -> dict | None`, `put(kind, params, body, path=None, ts=None) -> None`,
  `prune(ttl, path=None) -> int`, `_db_path(path=None) -> str`, `_connect(path=None) -> sqlite3.Connection`.

- [ ] **Step 1: Write the failing self-check**

Create `poc/scrape_cache.py`. Put the module docstring + imports + the self-check FIRST (functions still undefined → fails):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python poc/scrape_cache.py --self-test`
Expected: FAIL / NameError — `put`/`get` not defined.

- [ ] **Step 3: Implement the module**

Insert above `_self_test`:

```python
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
    except (sqlite3.Error, OSError):
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python poc/scrape_cache.py --self-test`
Expected: PASS — "All checks passed." exit 0.

- [ ] **Step 5: Commit**

```bash
git add poc/scrape_cache.py
git commit -m "feat(poc): disposable SQLite scrape cache (get/put/prune, TTL, api_key-safe)"
```

---

### Task 2: Wrap `_scraperapi_structured` + engine self-test

**Files:**
- Modify: `poc/naar_price_poc.py` — cache check + store in `_scraperapi_structured`; add `_test_scrape_cache(check)` and register it in `self_test()`.
- Test: `python poc/naar_price_poc.py --self-test`

**Interfaces:**
- Consumes: Task 1's `scrape_cache.enabled/ttl/get/put`.
- Produces: `_scraperapi_structured` now cache-backed (same signature, same return/raise contract).

- [ ] **Step 1: Read the current function**

Read `poc/naar_price_poc.py` around `def _scraperapi_structured` (it: guards `requests`/key, GETs, checks 403-credits / HTTP≥400, `body = r.json()` (raises `SourceError` on non-JSON), `if not isinstance(body, dict): raise SourceError(...)`, then `return body`). Note the exact final lines so the cache-store goes right before `return body`.

- [ ] **Step 2: Write the failing test group**

Add above `def self_test()` (near the other `_test_*`):

```python
def _test_scrape_cache(check):
    """A cached response is returned WITHOUT network; SCRAPE_CACHE=off bypasses it."""
    import tempfile as _tf
    import scrape_cache as _sc
    saved_db = os.environ.get("SCRAPE_CACHE_DB")
    saved_on = os.environ.get("SCRAPE_CACHE")
    fd, dbp = _tf.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["SCRAPE_CACHE_DB"] = dbp
    os.environ["SCRAPE_CACHE"] = "on"
    try:
        fake = {"sold_by": "CACHED CO", "pricing": "₹1"}
        _sc.put("amazon/product", {"asin": "ZCACHE"}, fake)
        # cache hit -> returns fake, NO network (works even if requests is importable)
        got = _scraperapi_structured("amazon/product", {"asin": "ZCACHE"})
        check("cached structured response served without network", got == fake)
        # bypass: with cache off and no live path available, it must NOT return the cached value
        os.environ["SCRAPE_CACHE"] = "off"
        bypassed = True
        try:
            r = _scraperapi_structured("amazon/product", {"asin": "ZCACHE"})
            bypassed = (r != fake)        # if it somehow returns, it must not be the cached body
        except SourceError:
            bypassed = True               # expected: no key/requests -> live path raises
        check("SCRAPE_CACHE=off bypasses the cache", bypassed)
    finally:
        os.environ.pop("SCRAPE_CACHE_DB", None)
        os.environ.pop("SCRAPE_CACHE", None)
        if saved_db is not None:
            os.environ["SCRAPE_CACHE_DB"] = saved_db
        if saved_on is not None:
            os.environ["SCRAPE_CACHE"] = saved_on
        for p in (dbp, dbp + "-wal", dbp + "-shm"):
            try:
                os.remove(p)
            except OSError:
                pass
```

Register it in `self_test()` after `_test_auto_confirm(check)`:

```python
    _test_auto_confirm(check)
    _test_scrape_cache(check)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python poc/naar_price_poc.py --self-test`
Expected: FAIL — `_scraperapi_structured` still fetches (cache not wired), so the "served without network" check fails (raises `SourceError` credits/requests, or the cache is ignored).

- [ ] **Step 4: Wire the cache into `_scraperapi_structured`**

At the TOP of `_scraperapi_structured` (first lines of the body, before the `requests is None` guard) add:

```python
    import scrape_cache
    if scrape_cache.enabled():
        _hit = scrape_cache.get(kind, params, scrape_cache.ttl())
        if _hit is not None:
            return _hit
```

Then, immediately BEFORE the final `return body` (after the `if not isinstance(body, dict): raise SourceError(...)` guard), add:

```python
    if scrape_cache.enabled():
        scrape_cache.put(kind, params, body)
    return body
```

(Leave every existing `SourceError` raise as-is — they sit between the cache-check and the store, so failures are never cached.)

- [ ] **Step 5: Run to verify it passes**

Run: `python poc/naar_price_poc.py --self-test`
Expected: PASS — the 2 new cache checks green, plus all prior checks.

- [ ] **Step 6: Commit**

```bash
git add poc/naar_price_poc.py
git commit -m "feat(poc): cache-back _scraperapi_structured (hit -> no network; only success cached)"
```

---

### Task 3: gitignore + docs + full verify

**Files:**
- Modify: `poc/.gitignore`, `poc/README.md`
- Test: full offline suite.

- [ ] **Step 1: Ignore the cache DB**

Append to `poc/.gitignore`:

```
scrape_cache.db
scrape_cache.db-wal
scrape_cache.db-shm
```

- [ ] **Step 2: Document it**

Add to `poc/README.md`, in the Environment section (or just after it):

```markdown
### Scrape cache

Successful ScraperAPI responses are cached in `poc/scrape_cache.db` (SQLite,
gitignored, **disposable** — delete it to force a fresh re-scrape). Repeat
discovery / price-match runs of the same product are then instant and cost no
credits. Env: `SCRAPE_CACHE=off` bypasses it; `SCRAPE_CACHE_TTL` (seconds,
default 604800 = 7 days) sets freshness; `SCRAPE_CACHE_DB` overrides the path.
Only successful responses are cached; the cache never breaks a live fetch.
```

- [ ] **Step 3: Full offline suite**

```bash
python poc/scrape_cache.py --self-test && \
python poc/results_store.py --self-test && \
python poc/naar_price_poc.py --self-test && \
python poc/eval_accuracy.py && \
python poc/prove_llm.py && \
python -m py_compile poc/*.py && echo "ALL GREEN"
```

Expected: every step passes; ends `ALL GREEN`. Also `git check-ignore poc/scrape_cache.db` prints the path (ignored).

- [ ] **Step 4: Commit**

```bash
git add poc/.gitignore poc/README.md
git commit -m "chore(poc): ignore scrape_cache.db; document the scrape cache"
```

---

## Self-Review

**Spec coverage:** cache module (get/put/prune/TTL/bypass) — Task 1; wrap at the single choke point, only-success cached, hit→no-network — Task 2; separate gitignored DB + docs — Tasks 1/3; api_key-safe key + cache-never-breaks-fetch — Tasks 1 (tests) + 2. ✓

**Placeholder scan:** every step has full code + exact commands/expected output. ✓

**Type consistency:** `get(kind, params, ttl, path)` / `put(kind, params, body, path, ts)` / `cache_key(kind, params)` used identically in the module, the engine wrap, and both self-tests. `enabled()`/`ttl()` used in the wrap exactly as defined. ✓

**Ordering note:** Task 2's `_test_scrape_cache` imports `scrape_cache` (exists from Task 1) — run tasks in order.
