#!/usr/bin/env bash
# Enable live production mode (Naar shop + Claude + real competitor scraping)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/backend/.env"

echo "Naar Price Monitor — Production setup"
echo "======================================"
echo ""

if [ -f "$ENV_FILE" ] && grep -q "^ANTHROPIC_API_KEY=sk-ant-" "$ENV_FILE" 2>/dev/null; then
  echo "Found existing .env with Anthropic key."
else
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    KEY="$ANTHROPIC_API_KEY"
    echo "Using ANTHROPIC_API_KEY from your shell environment."
  else
    echo "Get an API key from: https://console.anthropic.com/settings/keys"
    echo ""
    read -rsp "Paste your Anthropic API key (sk-ant-...): " KEY
    echo ""
    if [ -z "$KEY" ]; then
      echo "ERROR: API key required for production mode."
      exit 1
    fi
  fi

  cat > "$ENV_FILE" <<EOF
# Production — live Naar shop + Claude matching
ANTHROPIC_API_KEY=$KEY
PRODUCTION_MODE=true
DEMO_MODE=false
USE_CLAUDE=true
CLAUDE_MODEL=claude-sonnet-4-20250514

NAAR_SHOP_URL=https://naar.io/shop
NAAR_BASE_URL=https://naar.io

# Optional — improves Amazon / Flipkart scraping
BRIGHTDATA_PROXY=
SCRAPERAPI_KEY=

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/naar_monitor
REDIS_URL=redis://localhost:6379/0
MIN_MATCH_CONFIDENCE=0.75
EOF
  echo "Wrote $ENV_FILE"
fi

echo ""
echo "Installing Playwright browser (for naar.io/shop scraping)…"
cd "$ROOT/backend"
source .venv/bin/activate
pip install -q anthropic playwright 2>/dev/null || pip install anthropic playwright
playwright install chromium 2>/dev/null || true

echo ""
echo "Restarting backend…"
pkill -f "uvicorn api.main:app" 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload &
sleep 3

HEALTH=$(curl -sf http://127.0.0.1:8000/health || echo "")
if echo "$HEALTH" | grep -q '"production_mode":true'; then
  echo ""
  echo "✓ Production mode ACTIVE"
  echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
  echo ""
  echo "Next: refresh http://localhost:3000 and click Run Scan Now"
else
  echo ""
  echo "Backend running but production_mode not active yet. Check:"
  echo "  curl http://127.0.0.1:8000/health"
  echo "$HEALTH"
fi
