#!/usr/bin/env python3
"""Turn a run's results.jsonl into a clean, shareable CSV (Excel / Google Sheets).

Usage: python make_sheet.py <out_dir> [sheet.csv]
Produces business-readable columns + a summary header, from the raw records.
"""
import csv
import json
import os
import sys

STATUS_LABEL = {
    "MATCHED": "✅ Match found (same product + seller)",
    "SOLD_BY_OTHER": "🔵 On marketplace — different seller",
    "AMBIGUOUS_MATCH": "🟡 Uncertain — needs review",
    "PRODUCT_NOT_FOUND": "⚪ Not on marketplace",
    "OUT_OF_STOCK": "⛔ Match, out of stock",
    "SOURCE_ERROR": "⚠️ Could not fetch",
}

COLUMNS = [
    ("Naar product", lambda r: r.get("_title", "")),
    ("Variant", lambda r: r.get("_variant", "")),
    ("Naar seller", lambda r: r.get("_seller", "")),
    ("Naar price (₹)", lambda r: _money(r.get("naar_selling_price"))),
    ("Marketplace", lambda r: r.get("marketplace", "")),
    ("Result", lambda r: STATUS_LABEL.get(r.get("status", ""), r.get("status", ""))),
    ("Marketplace price (₹)", lambda r: _money(r.get("marketplace_selling_price"))),
    ("Per-unit price (₹)", lambda r: _money(r.get("marketplace_unit_price"))),
    ("Δ vs Naar (₹)", lambda r: _delta(r)),
    ("Confirmed seller", lambda r: r.get("marketplace_sold_by") or ""),
    ("Also sold by (competitors + price)", lambda r: r.get("other_sellers") or ""),
    ("Listing", lambda r: r.get("listing_url") or ""),
    ("Notes", lambda r: r.get("match_evidence") or ""),
    ("Checked (UTC)", lambda r: r.get("observed_at", "")),
]


def _money(v):
    try:
        return f"{float(v):.2f}" if v not in (None, "") else ""
    except (TypeError, ValueError):
        return ""


def _delta(r):
    try:
        base = r.get("marketplace_unit_price") or r.get("marketplace_selling_price")
        if base in (None, "") or r.get("naar_selling_price") in (None, ""):
            return ""
        return f"{float(base) - float(r['naar_selling_price']):+.2f}"
    except (TypeError, ValueError):
        return ""


def main():
    if len(sys.argv) < 2:
        print("usage: python make_sheet.py <out_dir> [sheet.csv]", file=sys.stderr)
        raise SystemExit(2)
    out_dir = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else os.path.join(out_dir, "naar_price_match_sheet.csv")
    rows = []
    with open(os.path.join(out_dir, "results.jsonl"), encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    for r in rows:
        r["_title"] = r.get("naar_product_title") or r.get("naar_product_id", "")
        r["_variant"] = r.get("naar_variant_name") or "-"
        r["_seller"] = r.get("naar_seller_name") or r.get("naar_seller_id", "")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    n = len(rows) or 1

    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Naar marketplace price-match — results"])
        w.writerow([f"Total rows: {len(rows)} (product×marketplace)"])
        for s in ("MATCHED", "SOLD_BY_OTHER", "AMBIGUOUS_MATCH",
                  "PRODUCT_NOT_FOUND", "OUT_OF_STOCK", "SOURCE_ERROR"):
            if counts.get(s):
                w.writerow([f"{STATUS_LABEL[s]}: {counts[s]} ({counts[s]/n*100:.0f}%)"])
        w.writerow([])
        w.writerow([c[0] for c in COLUMNS])
        # matches first, then other-seller intel, then the rest
        order = {"MATCHED": 0, "SOLD_BY_OTHER": 1, "AMBIGUOUS_MATCH": 2,
                 "OUT_OF_STOCK": 3, "PRODUCT_NOT_FOUND": 4, "SOURCE_ERROR": 5}
        for r in sorted(rows, key=lambda x: (order.get(x["status"], 9), x.get("marketplace", ""))):
            w.writerow([fn(r) for _, fn in COLUMNS])

    print(f"wrote {dest} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
