# Naar Price Monitor

Full-stack AI price parity system for Naar — implemented from `naar-price-monitor-implementation-guide.md`.

## Stack

- **Backend:** Python 3.12, FastAPI, Celery, Playwright, RapidFuzz (+ optional sentence-transformers)
- **Database:** PostgreSQL 16, Redis 7.4
- **Frontend:** Next.js 15, TanStack Table/Query, Recharts
- **Schedule:** Weekly full scan (Monday 6:00 AM IST) + 4-hourly critical refresh

## Quick Start (Demo Mode)

Demo mode works without Postgres, proxies, or API keys.

```bash
cd naar-price-monitor
cp .env.example .env

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_scan.py          # Manual scan (demo data)

# API (separate terminal)
uvicorn api.main:app --reload --port 8000

# Frontend (separate terminal)
cd ../frontend
npm install && npm run dev
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Full Production Setup

```bash
cp .env.example .env   # Set DATABASE_URL, REDIS_URL, proxy keys
docker compose up -d
```

Services:
| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| Flower (Celery) | http://localhost:5555 |

### Manual scan via API

```bash
curl -X POST http://localhost:8000/reports/run-scan
```

### Celery manual trigger

```bash
docker compose exec celery-worker celery -A tasks.celery_app call tasks.crawl_tasks.run_full_price_check
```

## Project Structure

```
naar-price-monitor/
├── backend/          # FastAPI + scrapers + matcher + Celery
├── frontend/         # Next.js dashboard
├── docker-compose.yml
└── .env.example
```

## Production Checklist

1. Set `DEMO_MODE=false` in `.env`
2. Configure `BRIGHTDATA_PROXY` for Amazon
3. Configure `SCRAPERAPI_KEY` for Flipkart
4. Set `SENDGRID_API_KEY` and `SLACK_WEBHOOK_URL`
5. Optionally set `USE_EMBEDDINGS=true` for semantic matching
6. Run discovery phase (see implementation guide §15)

## Weekly Cron

Celery Beat runs `run_full_price_check` every **Monday at 6:00 AM IST**.
