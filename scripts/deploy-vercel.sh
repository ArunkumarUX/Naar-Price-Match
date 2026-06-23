#!/usr/bin/env bash
# Deploy Naar Price Monitor frontend to Vercel (grethena-apps team).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -d .vercel ]]; then
  vercel link --yes --project naar-price-monitor
fi

vercel deploy --prod --yes --force \
  --env BACKEND_API_URL="${BACKEND_API_URL:-https://naar-api.onrender.com}"

echo ""
echo "Production URLs (use these):"
echo "  https://naar-price-monitor.vercel.app"
echo "  https://naar-price-monitor-grethena-apps.vercel.app"
echo ""
echo "Note: project-mf3h0.vercel.app may 404 — use naar-price-monitor.vercel.app instead."
echo ""
echo "Health check:"
echo "  https://naar-price-monitor.vercel.app/backend-api/health"
