#!/usr/bin/env bash
# Fix "Internal Server Error" — kills stale Next/uvicorn and starts fresh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping stale processes on ports 3000–3003 and 8000…"
pkill -f "uvicorn api.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
for p in 3000 3001 3002 3003 8000; do
  for _ in 1 2 3 4 5; do
    lsof -ti:"$p" | xargs kill -9 2>/dev/null || true
    sleep 1
    lsof -ti:"$p" >/dev/null 2>&1 || break
  done
done
if lsof -ti:3000 >/dev/null 2>&1; then
  echo "ERROR: Port 3000 is still in use. Run in Terminal:"
  echo "  lsof -ti:3000 | xargs kill -9"
  echo "Then re-run this script."
  exit 1
fi
sleep 1

echo "Clearing corrupted Next.js cache…"
rm -rf "$ROOT/frontend/.next"

printf 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000\n' > "$ROOT/frontend/.env.local"

echo "Starting backend http://127.0.0.1:8000 …"
cd "$ROOT/backend"
source .venv/bin/activate
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload &
sleep 3

echo "Building frontend (production)…"
cd "$ROOT/frontend"
npm run build

echo "Starting frontend http://127.0.0.1:3000 …"
npm run start
