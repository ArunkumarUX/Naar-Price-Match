#!/usr/bin/env bash
# Import bundled Naar catalog JSON into production (or local) API.
set -euo pipefail

API_URL="${1:-https://naar-api.onrender.com}"
SEED="${2:-$(cd "$(dirname "$0")/.." && pwd)/data/naar-catalog-seed.json}"

echo "→ Importing catalog from $SEED"
echo "→ Target: $API_URL/products/import-catalog"

curl -sS -X POST "$API_URL/products/import-catalog" \
  -H "Content-Type: application/json" \
  --data-binary "@$SEED" | python3 -m json.tool

echo ""
echo "→ Products in database:"
curl -sS "$API_URL/products/?limit=5" | python3 -m json.tool
