# Design — ScraperAPI response cache

Date: 2026-07-27
Scope: new `poc/scrape_cache.py`; wrap `_scraperapi_structured` in `poc/naar_price_poc.py`
Status: approved in brainstorming; pending spec review

## Problem

Every store discovery (Verify / auto-confirm sweep) and every price-match run re-fetches
the **same** ScraperAPI structured responses (`amazon/search`, `amazon/product`) from the
paid API — even for products already fetched moments ago. This makes repeats slow (~3–4s per
structured render, e.g. Sirpika discovery took ~33s) and expensive (a full-catalogue re-scrape
≈ 15,700 paid calls, all of it re-paid on every run). We persist *answers* (`results.db`) and
*decisions* (`seller_identity.json`) but not the *raw inputs*.

## Decisions (from brainstorming)

1. **Single TTL, default 7 days** — one TTL for both search + product responses, env
   `SCRAPE_CACHE_TTL` (seconds, default 604800). Entries older than the TTL are re-fetched.
2. **Bypass / refresh** — `SCRAPE_CACHE=off` disables the cache entirely (always fetch, never
   store). This is the "force fresh" escape.
3. **Separate disposable DB** — `poc/scrape_cache.db` (SQLite, gitignored, env
   `SCRAPE_CACHE_DB`). Deleting it forces a full fresh re-scrape without touching `results.db`
   or the registry.
4. **Single choke point** — wrap `_scraperapi_structured` (all search + product calls go
   through it); one wrap covers discovery + scan.

Rejected: split search/product TTLs (more code, not needed for a POC); a table inside
`results.db` (mixes disposable cache with durable results); no-expiry (stale prices).

## How it works

```
_scraperapi_structured(kind, params):        # params = {"query": q} or {"asin": a} — NO api_key
   cache ON and a fresh entry exists?  -> return cached body (no network, no credit)
   else -> fetch from ScraperAPI (existing code) -> validate dict -> store in cache -> return
```

The `params` argument is already clean (the api_key/country/tld are added *inside*
`_scraperapi_structured`), so the cache key never contains the secret. Only **successful**
dict responses are cached — errors (`SourceError`: credits exhausted, non-JSON, non-dict, HTTP
≥400) raise before the store step and are never cached.

## Storage & schema (`poc/scrape_cache.db`, gitignored)

New stdlib-`sqlite3` module `poc/scrape_cache.py`, tested via a temp DB.

```sql
cache(
  key TEXT PRIMARY KEY,     -- sha256(kind + json.dumps(params, sort_keys=True))
  kind TEXT,                -- "amazon/search" | "amazon/product"
  params TEXT,              -- json of the clean params (audit/debug)
  body TEXT,                -- json of the response dict
  fetched_at INTEGER        -- epoch seconds
)
-- index: cache(fetched_at)  (for prune)
```

API:
- `enabled() -> bool` — `os.environ.get("SCRAPE_CACHE","on") != "off"`.
- `ttl() -> int` — `int(os.environ.get("SCRAPE_CACHE_TTL", "604800"))`.
- `cache_key(kind, params) -> str` — sha256 hex of `kind + "\n" + json.dumps(params, sort_keys=True, ensure_ascii=False)`.
- `get(kind, params, ttl, path=None) -> dict | None` — the stored body dict if a row exists and
  `now - fetched_at < ttl` (ttl <= 0 → always a miss); else None. JSON-decodes `body`.
- `put(kind, params, body, path=None, ts=None) -> None` — `INSERT OR REPLACE`; `ts` defaults to
  now (tests pass an explicit old `ts` to simulate expiry).
- `prune(ttl, path=None) -> int` — delete rows older than ttl; returns count (housekeeping, optional to call).
- `stats(path=None) -> dict` — `{rows, bytes}` for a `/api/cache` debug view (optional).
- `_db_path`, `_connect` — resolve `$SCRAPE_CACHE_DB` else `poc/scrape_cache.db`; WAL +
  `busy_timeout=5000` (concurrent discovery/scan threads read+write).

Concurrency: per-call connections (like `results_store`), WAL, `INSERT OR REPLACE` — safe for
the parallel product fetches.

## The wrap (`naar_price_poc.py`)

`_scraperapi_structured(kind, params)` gains a cache check at the top and a store before the
final `return body`:

```python
def _scraperapi_structured(kind, params):
    import scrape_cache
    if scrape_cache.enabled():
        hit = scrape_cache.get(kind, params, scrape_cache.ttl())
        if hit is not None:
            return hit
    # ... existing fetch + validation (raises SourceError on any failure) ...
    if not isinstance(body, dict):
        raise SourceError(...)
    if scrape_cache.enabled():
        scrape_cache.put(kind, params, body)
    return body
```

Import inside the function (or at top) — `scrape_cache` is a sibling module; `naar_price_poc`
is imported as `poc` by `verify_app`, and both run from `poc/`.

## Error handling

- Cache miss / disabled → behaves exactly as today.
- A cache-layer failure (corrupt/locked cache.db) must **never** break a fetch — `get`/`put`
  swallow their own `sqlite3.Error`/`OSError` and fall through to the live path (the cache is an
  optimization, not a source of truth). This is the one place we deliberately swallow.
- Only success is cached; `SourceError` paths never reach `put`.

## Testing (offline, deterministic, no network)

`scrape_cache.py --self-test` (temp DB):
- `put`/`get` round-trips a dict body.
- `get` returns None when the row is older than ttl (via `put(..., ts=now-ttl-1)`), and the
  body when fresh.
- `ttl<=0` → always miss; `enabled()`/`ttl()` honor the env vars.
- `cache_key` is stable for the same params and **excludes** any api_key (params never carry it).
- A cache-layer error path (bad db path) → `get` returns None / `put` no-ops, never raises.

In `naar_price_poc.py --self-test`, a `_test_scrape_cache(check)` group:
- Point `SCRAPE_CACHE_DB` at a temp file, `put` a fake `amazon/product` response, then call
  `_scraperapi_structured("amazon/product", {"asin": "X"})` and assert it returns the cached
  body **without any network** (works even with `requests` available — the hit short-circuits).
- With `SCRAPE_CACHE=off`, the same call ignores the cache (and, with no key, raises the usual
  `SourceError` — proving bypass).

## Files

- **create** `poc/scrape_cache.py` — the cache module (+ `--self-test`).
- **modify** `poc/naar_price_poc.py` — wrap `_scraperapi_structured`; add `_test_scrape_cache`.
- **modify** `poc/.gitignore` — add `scrape_cache.db` + `-wal`/`-shm`.
- **modify** `poc/README.md` — a short "Scrape cache" note (env vars, disposable, TTL).
- **(optional)** `poc/verify_app.py` — `GET /api/cache` (rows/bytes) + a tiny "cached N responses"
  line; deferrable.

## Out of scope (YAGNI)

- Split/per-endpoint TTLs; LRU eviction (prune-by-age is enough); cross-run analytics.
- Caching non-ScraperAPI calls (Naar catalogue is a free GET — not worth caching).
- A UI cache manager beyond an optional stats line.
