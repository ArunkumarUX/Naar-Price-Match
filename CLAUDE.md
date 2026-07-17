# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Two codebases coexist — only one is live

- **Active app:** TypeScript/Node backend in `src/` + Next.js frontend in `frontend/`. All recent commits, the root `package.json`, `Dockerfile`, `render.yaml`, and `docker-compose.yml` target this stack.
- **Legacy/dead:** the Python FastAPI app in `backend/` (Celery, uvicorn, `run_scan.py`). **`README.md` documents this dead stack — do not follow its Quick Start.** Nothing builds or deploys `backend/`. Only `backend/data/sellers.json` is still read (as a fallback path by `src/scrapers/seller.registry.ts`).
- **Also dead:** parts of `scripts/` drive the Python backend (see [Deployment](#deployment)). Treat `README.md` as stale; this file is the source of truth for the running system.

## Commands

Backend (run from repo root — this is `naar-price-monitor`):

```bash
npm run dev            # API with hot reload (tsx watch) → http://localhost:8000
npm run worker:dev     # BullMQ worker with hot reload
npm run build          # tsc → dist/
npm run start          # run compiled API
npm run worker         # run compiled worker
npm run migrate        # prisma migrate dev (local schema changes)
npm run migrate:deploy # prisma migrate deploy (production/CI)
npm run db:push        # push schema without a migration
```

Frontend (run from `frontend/`):

```bash
npm run dev    # Next.js dev on 127.0.0.1:3000
npm run build
npm run lint
```

Full local stack (Postgres + Redis + api + worker + frontend):

```bash
docker compose up -d
```

**There is no test suite** (no `test` script, no test files). Verify changes by running the app.

Prisma note: the schema lives at `src/prisma/schema.prisma` (non-default path, set via the `prisma.schema` key in `package.json`). All prisma commands pick it up automatically.

## Architecture

Price-parity monitor: pull the Naar catalog, search competitor marketplaces + registered sellers for each product, compare prices, surface discrepancies in a dashboard.

**Runtime pieces**
- **API** — Fastify, entry `src/api/server.ts`, routes in `src/api/routes/` (`alerts`, `products`, `comparison`, `reports`). The API process **also** starts an in-process catalog-sync timer (`src/jobs/catalog-sync.scheduler.ts`); the worker does not.
- **Worker** — BullMQ over Redis, entry `src/jobs/worker.ts`. `src/jobs/queue.ts` registers three repeatable cron jobs (all `Asia/Kolkata`): `sync-catalog` (`30 1 * * *`), `daily-full-check` (`0 2 * * *`), `critical-refresh` (`15 */4 * * *`).
- **DB** — Postgres via Prisma (`src/lib/prisma.ts`). Models: `Product` → `ProductListing` → `PriceSnapshot`, plus `PriceAlert`. A `Product`'s id is a sha256 slice of its SKU (`src/services/catalog.ts`).
- **Frontend** — Next.js 15 App Router in `frontend/`, React Query + TanStack Table + Recharts.

**⚠️ Alerts and notifications are NOT wired**
- **`PriceAlert` rows are never created.** `src/api/routes/alerts.ts` only reads (`findMany`, `groupBy`) and resolves them; there is no `prisma.priceAlert.create/upsert/createMany` anywhere in `src/`, and neither `price-check.job.ts` nor `price.comparator.ts` reference alerts. The engine classifies deviations but never persists a `PriceAlert`, so the alerts endpoints and `frontend/app/alerts/page.tsx` are effectively always empty. `PriceAlert.notified` is never set. **Wiring alert generation is unimplemented work, not a bug to hunt.**
- **`src/notifications/email.ts` (SendGrid) and `slack.ts` are dead code** — exported but imported by nobody. Their env vars (`SENDGRID_API_KEY`, `ALERT_EMAIL_FROM`/`TO`, `SLACK_WEBHOOK_URL`) are unused outside those two files. There is no end-to-end alerting pipeline today.

**Data flow**
1. `syncNaarCatalog()` (`src/services/catalog.ts`) upserts `Product` rows via a **4-stage source cascade** in `src/scrapers/naar.scraper.ts`, first non-empty wins: (1) `NAAR_CATALOG_API` — actually ~11 base URLs × 4 query suffixes built by `catalogApiCandidates` (`naar-catalog.fetch.ts`); (2) live shop Playwright scrape (`naar-shop.playwright.ts`); (3) Shopify `/products.json`; (4) direct Chromium walk of `NAAR_SHOP_URL` parsing JSON-LD (`source: playwright_ldjson`). **Stages 2 and 4 call `chromium.launch` with no `USE_PLAYWRIGHT` guard**, so on Render (where `USE_PLAYWRIGHT` is forced false) they still attempt to launch Chromium and fail — they only run if stages 1 and 3 both return nothing.
2. Manual seed import is a **separate path**: `data/naar-catalog-seed.json` is *not* read by `syncNaarCatalog`; it's POSTed to `/products/import-catalog` (`src/api/routes/products.ts`), driven by `scripts/import-catalog-production.sh`. Used as a fallback when sync returns `imported: 0`.
3. `runFullPriceCheck()` (`src/jobs/price-check.job.ts`) — for each product, searches Amazon/Flipkart/Meesho (`src/scrapers/marketplace.scraper.ts`) and optionally sellers, matches candidates, writes `ProductListing` + `PriceSnapshot`. Marketplace results are persisted before sellers run so the UI shows data early. Scan progress is tracked in-memory via `src/jobs/scan-status.ts`.
4. `GET /comparison/matrix` (`src/api/routes/comparison.ts`) reads the latest snapshot per listing and builds rows via `buildComparisonRow` / `classifyChannel` (`src/engine/price.comparator.ts`).

**Matching** (`src/matcher/product.matcher.ts`): `sku_exact` → `title_fuzzy` (Fuse.js) → `embedding` (Xenova transformers, **dev only**). Gated by `MIN_MATCH_CONFIDENCE`.

**Price classification** (`src/engine/price.comparator.ts`): deviation vs `MAX_PRICE_DEVIATION_PCT` yields `lower` / `higher` / `violation` (MAP) / `ok` / `missing`.

**Competitor scrape mode** — two orders that don't match, so read carefully:
- **Label/status** (`src/lib/scrape-mode.ts`, what `/health` and scan messages report): `SCRAPERAPI_KEY` → `USE_PLAYWRIGHT` → search links.
- **Actual price fetch** (`searchPlatform` in `src/scrapers/marketplace.scraper.ts`): checks `USE_PLAYWRIGHT` **first**, then `SCRAPERAPI_KEY`, then fallback. So locally with both set, Playwright fetches even though `competitorScrapeMode()` reports `scraperapi`. (Moot in prod — `USE_PLAYWRIGHT` forced false.)
- **Fallback always degrades gracefully:** if the chosen scraper returns empty or throws — *including when `SCRAPERAPI_KEY` is set but ScraperAPI yields zero rows* — `searchPlatform` emits search-link placeholders (`is_search_link: true`) instead of erroring. ScraperAPI HTML parsers live in `src/scrapers/marketplace.scraperapi.ts`.

## Production gotchas

- **`src/lib/config.ts` force-overrides env vars when `NODE_ENV=production`**, regardless of what you set: `USE_EMBEDDINGS=false`, `USE_PLAYWRIGHT=false`, `SKIP_SELLER_SCAN=true`. Embeddings (ONNX native) and Playwright OOM/crash on the Render free tier. Use ScraperAPI for live prices there. (Caveat: the catalog Playwright stages above ignore this flag.)
- **Config defaults differ from production `render.yaml`** — cross-check all three of `config.ts`, `.env.example`, `render.yaml` before trusting a default: `MIN_MATCH_CONFIDENCE` is `0.75` in config/`.env.example` but `0.45` in prod (looser fuzzy matching); `SELLER_SCAN_LIMIT` is `3` in config but `0` in prod, and absent from `.env.example`.
- **Env validation is Zod (`src/lib/config.ts`) — with one exception.** Add new env vars to the schema there. But `CATALOG_SYNC_INTERVAL_MS` is read directly via `process.env` in `catalog-sync.scheduler.ts` (default 30 min), bypassing the schema and `.env.example`; it affects only the API process and is set on `naar-api` in `render.yaml`.
- **ESM/NodeNext**: TypeScript source imports use explicit `.js` extensions (e.g. `import { config } from "../lib/config.js"`). Keep this or builds/imports break.

## Deployment

- **API + worker + Redis + Postgres → Render** via `render.yaml` (Docker, root `Dockerfile`, Node 22 Alpine with system Chromium). **Both** the API (`Dockerfile` CMD) and the worker (`render.yaml` `dockerCommand`) run `npx prisma migrate deploy` on boot; whichever container starts first migrates (Prisma advisory locks make this safe).
- **Frontend → Vercel** (`frontend/vercel.json`). API base resolution (`frontend/lib/api.ts`, `backend-url.ts`) is **env-var-first**: `NEXT_PUBLIC_API_URL` / `BACKEND_API_URL` win over any prod/dev logic. Only when unset does the fallback apply — browser calls the Render API directly in prod and the `/backend-api/[...path]` proxy in dev. Two caveats: the CSV export is a hardcoded `href="/backend-api/alerts/export/csv"` (`frontend/app/page.tsx`) that **always** goes through the proxy, even in prod; and the Render fallback URL `https://naar-api.onrender.com` is hardcoded in **three** places (`api.ts` ×2, `backend-url.ts`) — change all three or set the env vars.
- **`scripts/` is split** — several target the dead Python backend: `enable-production.sh` and `fix-500.sh` write `backend/.env` / kill `uvicorn` and reference `ANTHROPIC_API_KEY`/`USE_CLAUDE`/`CLAUDE_MODEL` vars the TS app ignores. **Do not run them.** Live-stack scripts: `import-catalog-production.sh` (seed → `/products/import-catalog`), `sync-catalog.sh` (`POST /reports/sync-catalog`), `deploy-vercel.sh`. `scraperapi-marketplaces.py` is a standalone parser reference.

## Frontend design

`DESIGN.md` holds the Naar brand system (colour tokens, typography, motion, component rules). Follow it for any UI work; brand tokens are mirrored in `frontend/lib/brand.ts`.
