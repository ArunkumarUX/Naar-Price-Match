#!/usr/bin/env python3
"""Fetch Amazon.in, Flipkart, and Meesho pages via ScraperAPI."""

from __future__ import annotations

import os
import sys

import requests

MARKETPLACES = {
    "amazon": "https://www.amazon.in/",
    "flipkart": "https://www.flipkart.com/",
    "meesho": "https://www.meesho.com/",
}

SEARCH_URLS = {
    "amazon": "https://www.amazon.in/s?k={query}",
    "flipkart": "https://www.flipkart.com/search?q={query}",
    "meesho": "https://www.meesho.com/search?q={query}",
}


def fetch(url: str, api_key: str) -> str:
    response = requests.get(
        "http://api.scraperapi.com",
        params={
            "api_key": api_key,
            "url": url,
            "render": "true",
            "country_code": "in",
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.text


def main() -> int:
    api_key = os.environ.get("SCRAPERAPI_KEY", "").strip()
    if not api_key:
        print("Set SCRAPERAPI_KEY in your environment.", file=sys.stderr)
        return 1

    query = sys.argv[1] if len(sys.argv) > 1 else "ginger pickle"

    urls = [
        SEARCH_URLS["amazon"].format(query=query),
        SEARCH_URLS["flipkart"].format(query=query),
        SEARCH_URLS["meesho"].format(query=query),
    ]

    # Also probe marketplace homepages
    urls.extend(MARKETPLACES.values())

    for url in urls:
        print(f"\n=== {url} ===")
        try:
            html = fetch(url, api_key)
            print(f"OK — {len(html):,} bytes")
            if "₹" in html:
                snippet = html[html.find("₹") : html.find("₹") + 20]
                print(f"Sample price snippet: {snippet}")
        except requests.RequestException as exc:
            print(f"ERROR — {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
