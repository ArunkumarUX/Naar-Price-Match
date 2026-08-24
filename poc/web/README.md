# Naar price-match — web frontend (POC)

A Next.js 15 frontend for the POC, over the `verify_app` backend. **Annotate**
marketplace stores (Verify → Confirm/Not-on/paste-URL, plus the high-similarity
auto-confirm sweep) and view **Results** (Finalize & run → filterable price-match
table → Download CSV). Naar-branded (tokens from `DESIGN.md`), light/dark.

Separate from the production `frontend/` app on purpose — it targets the POC's
`verify_app` backend, not the TypeScript service.

## Run

Two processes:

```bash
# 1) the POC backend (serves the API this frontend proxies to)
python poc/verify_app.py                 # http://127.0.0.1:8765   (--fixture for offline demo)

# 2) the frontend
cd poc/web
npm install
npm run dev                              # http://127.0.0.1:3007
```

The browser calls `/poc-api/*`, which Next rewrites server-side to the backend
(`http://127.0.0.1:8765/api/*`) — so no CORS is needed and `verify_app` is
unchanged. Point at a deployed backend with `POC_BACKEND=https://…`.

## Build / deploy

```bash
npm run build && npm start               # production build on :3007
```

Deployable to Vercel; set `POC_BACKEND` to a reachable `verify_app` URL. (The
backend itself is a stdlib server — host it wherever Python runs.)

## Layout
- `app/page.tsx` — Annotate (seller table, Verify/Confirm/Reject, sweep panel)
- `app/results/page.tsx` — Results (run panel, filter/sort table, CSV)
- `components/` — `Shell` (nav + theme), `StatusPill`, `SweepPanel`
- `lib/api.ts` — typed client over `/poc-api/*`; `lib/types.ts`, `lib/format.ts`
- `next.config.js` — the `/poc-api → backend` proxy
