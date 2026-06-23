#!/usr/bin/env bash
# Sync Naar catalog from NAAR_CATALOG_API (production best practice).
set -euo pipefail

API_URL="${1:-http://localhost:8000}"

echo "→ Syncing catalog from NAAR_CATALOG_API via ${API_URL}/reports/sync-catalog"
curl -sS -X POST "${API_URL}/reports/sync-catalog" | python3 -m json.tool

echo ""
echo "→ Product count"
curl -sS "${API_URL}/products/?limit=5" | python3 -m json.tool
