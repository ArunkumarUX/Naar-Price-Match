#!/usr/bin/env bash
# Restart dev servers with latest code (fixes stale API routes + corrupted Next cache)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping old dev processes…"
pkill -f "uvicorn api.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
for p in 3000 3001 3002 3003 8000 8001 8002; do
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

echo "Clearing Next.js cache…"
rm -rf "$ROOT/frontend/.next"

echo "Starting backend on http://127.0.0.1:8000 …"
cd "$ROOT/backend"
source .venv/bin/activate
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  if curl -sf http://127.0.0.1:8000/comparison/matrix >/dev/null 2>&1; then
    echo "Backend OK — comparison routes loaded."
    break
  fi
  if [ "$i" -eq 10 ]; then
    echo "ERROR: /comparison/matrix not available — port 8000 may still be blocked."
    kill "$BACKEND_PID" 2>/dev/null || true
    exit 1
  fi
done

echo "Starting frontend on http://127.0.0.1:3000 …"
cd "$ROOT/frontend"
printf 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000\n' > .env.local
npm run dev -- -H 127.0.0.1 -p 3000
