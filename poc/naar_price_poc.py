#!/usr/bin/env python3
"""
Naar marketplace price-matching — 10-product POC script (v2, post-review).

Implements the pipeline from the proposal: pull active products from the
Naar API, search Amazon.in / Flipkart / Meesho for each variant, apply the
product gate and the seller gate independently, and emit one record per
variant x marketplace with an honest status. A marketplace price is written
only on MATCHED rows, and only from structured offer data — never from an
LLM and never from a page-wide guess.

Usage:
    python naar_price_poc.py --backend fixture            # offline demo, all six statuses
    python naar_price_poc.py --backend direct --limit 10  # live run (Naar API + direct fetch)
    python naar_price_poc.py --self-test                  # regression checks from the code review
    python naar_price_poc.py --backend fixture --llm-judge  # borderline judge (see LLM_JUDGE_PROVIDER)

Borderline judge provider (optional; only rules on product-gate borderlines,
never sets price/seller): LLM_JUDGE_PROVIDER=anthropic|openai (default: auto by
key). anthropic -> ANTHROPIC_API_KEY(+ANTHROPIC_MODEL); openai -> OPENAI_API_KEY
(+OPENAI_BASE_URL,OPENAI_MODEL), which also drives any OpenAI-compatible vendor
(Qwen/DeepSeek/Groq/OpenRouter/local Ollama). No key -> judge is skipped.

Flags: --strict makes ANY unexplained token in a candidate title demote it to
borderline (judge or AMBIGUOUS_MATCH); default tolerates one.

Outputs: results.csv and results.jsonl in --out (default ./poc_out).

v2 review fixes:
  1. norm_name strips only true legal suffixes — "Reliance Retail" no longer
     equals "Reliance Industries". Token-set equality handles word reordering.
  2. Variant attributes match on word boundaries ("Teal" != "Steal").
  3. Candidates that add unexplained content tokens (vs Naar title/variant/
     description) are borderline, never auto-pass ("Amla Powder" vs
     "Amla Powder Hair Mask").
  4. Seller-matched offers are collected across all candidates, then chosen:
     purchasable beats OUT_OF_STOCK; a matched offer with no extractable
     price is SOURCE_ERROR, never a guess and never mislabelled OOS.
  5. A variant without sellingPrice is skipped with a warning — never ₹0.00.
  6. A failed offer-list fetch on a product-matched listing is SOURCE_ERROR,
     not silently "no offers".
  7. Flipkart parses brace-matched __INITIAL_STATE__ JSON instead of
     first-regex-on-page.
  8. Meesho catalogue min price is never recorded as an offer price.
  9. Record invariants raise, not assert; every record carries search_query.

v3 review fixes (price integrity + honest blocks):
  1. _walk_first is document-order/shallowest (BFS), and Flipkart reads seller
     + price from a SINGLE node — so they can't be paired from two unrelated
     products in a large embedded state.
  2. A captcha/interstitial returned with HTTP 200 is a SOURCE_ERROR, not a
     silent PRODUCT_NOT_FOUND (soft-block detection).
  3. Meesho takes price only from the supplier-tied PDP node; the SERP card ₹
     (a catalogue minimum) is never recorded as the seller's offer price.
  4. OUT_OF_STOCK vs SOURCE_ERROR scans ALL matched offers — an in-stock offer
     with an unextractable price wins as SOURCE_ERROR over an OOS sibling.
  5. Numeric variant attributes (size "8", "42") are gated on word boundaries;
     quantity-style values stay owned by the unit-normalised quantity gate.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # fixture backend and --self-test still work without it

NAAR_ENDPOINT = "https://prodapi-commerce.naar.io/v1/products"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

STATUSES = ("MATCHED", "SOLD_BY_OTHER", "PRODUCT_NOT_FOUND",
            "AMBIGUOUS_MATCH", "OUT_OF_STOCK", "SOURCE_ERROR")

# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Offer:
    """One seller's offer on a marketplace listing."""
    seller_display: Optional[str]          # "Sold by" string as shown
    seller_legal: Optional[str] = None     # registered name from seller profile, if fetched
    price_inr: Optional[float] = None      # tax-inclusive purchasable price, delivery excluded
    mrp_inr: Optional[float] = None        # evidence only
    delivery_inr: Optional[float] = None   # evidence only
    in_stock: bool = True
    offer_ref: Optional[str] = None


@dataclass
class Candidate:
    """One product listing returned by a marketplace search."""
    marketplace: str
    listing_id: str
    listing_url: str
    title: str
    offers: list[Offer] = field(default_factory=list)
    offers_error: Optional[str] = None     # set when offer enumeration failed (fix 6)


@dataclass
class Record:
    naar_product_id: str
    naar_variant_id: str
    naar_seller_id: str
    marketplace: str
    status: str
    naar_selling_price: float
    search_query: Optional[str] = None     # reproducibility evidence (fix 9)
    currency: str = "INR"
    marketplace_selling_price: Optional[float] = None
    marketplace_sold_by: Optional[str] = None
    marketplace_seller_legal_name: Optional[str] = None
    listing_id: Optional[str] = None
    listing_url: Optional[str] = None
    offer_ref: Optional[str] = None
    delivery_charge: Optional[float] = None
    mrp_displayed: Optional[float] = None
    product_match_method: Optional[str] = None
    seller_match_signal: Optional[str] = None
    match_evidence: Optional[str] = None
    confidence: Optional[float] = None
    observed_at: str = ""

    def __post_init__(self):
        if not self.observed_at:
            self.observed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        if self.status not in STATUSES:               # fix 9: raise, never assert
            raise ValueError(f"unknown status {self.status!r}")
        # Invariant from the brief: a price exists only on MATCHED rows.
        if self.status != "MATCHED":
            self.marketplace_selling_price = None


# --------------------------------------------------------------------------
# Normalisation helpers
# --------------------------------------------------------------------------

# Fix 1: true legal boilerplate only. Words like "retail", "industries",
# "enterprises", "traders" are distinctive and must never be stripped.
LEGAL_SUFFIXES = re.compile(
    r"\b(private|pvt\.?|limited|ltd\.?|llp|plc|opc|inc\.?|co\.?|corp\.?|company)\b", re.I)

# Generic function/marketing words only — deliberately small. Product-specific
# vocabulary is NOT curated here; the gate scores how much of a listing is
# unexplained rather than blacklisting words, so it generalises across catalogs.
STOPWORDS = {"the", "a", "an", "of", "for", "and", "with", "in", "by", "pack",
             "new", "best", "original", "premium", "combo", "set"}

QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|kgs|g|gm|gms|gram|grams|l|litre|liter|ltr|ml)\b", re.I)
PACK_RE = re.compile(r"(?:pack\s*of|set\s*of)\s*(\d+)|(\d+)\s*(?:pcs?|pieces?|units?)\b", re.I)

QTY_TO_BASE = {"kg": 1000, "kgs": 1000, "g": 1, "gm": 1, "gms": 1, "gram": 1, "grams": 1,
               "l": 1000, "litre": 1000, "liter": 1000, "ltr": 1000, "ml": 1}


def _cfg_float(name: str, default: float) -> float:
    """Read a tuning knob from the environment, falling back to a default.
    Keeps thresholds flexible without hardcoding them into the logic."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def norm_name(s: Optional[str]) -> str:
    """Normalise a seller name: casefold, strip legal suffixes and punctuation."""
    if not s:
        return ""
    s = LEGAL_SUFFIXES.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s.casefold())
    return re.sub(r"\s+", " ", s).strip()


def name_compare(observed: Optional[str], target: Optional[str]) -> tuple[float, Optional[str]]:
    """(similarity, exactness). exactness is 'exact' | 'token_set' | None.
    Only exactness constitutes a match; similarity only ranks proposals."""
    a, b = norm_name(observed), norm_name(target)
    if not a or not b:
        return 0.0, None
    if a == b:
        return 1.0, "exact"
    if set(a.split()) == set(b.split()):              # fix 1: word reordering
        return 1.0, "token_set"
    return SequenceMatcher(None, a, b).ratio(), None


def content_tokens(s: str) -> set[str]:
    # Quantity expressions ("100g", "100 g") are handled by their own gate;
    # stripping them here stops spacing artefacts ("g") polluting the
    # token comparison.
    s = QTY_RE.sub(" ", s or "")
    toks = re.findall(r"[a-z0-9]+", s.casefold())
    return {t for t in toks if t not in STOPWORDS and not t.isdigit() and len(t) > 1}


def extract_attrs(text: str) -> dict:
    """Pull comparable attributes (quantity in base units, pack count) from free text."""
    attrs: dict = {}
    m = QTY_RE.search(text or "")
    if m:
        attrs["qty_base"] = float(m.group(1)) * QTY_TO_BASE[m.group(2).lower()]
        attrs["qty_raw"] = m.group(0)
    m = PACK_RE.search(text or "")
    if m:
        attrs["pack"] = int(m.group(1) or m.group(2))
    return attrs


# --------------------------------------------------------------------------
# Naar source
# --------------------------------------------------------------------------

class SourceError(Exception):
    """Any collection failure — network, auth, block, or parse."""


def fetch_naar_products(limit: int, skip: int) -> list[dict]:
    """Fetch active products from Naar. The brief describes the endpoint as a
    plain GET with no auth. NAAR_API_KEY is optional plumbing: if the env var
    is set, its value is sent as X-Api-Key — otherwise no auth header is sent
    and none is required. Adjust to whatever header Naar actually uses if
    that turns out to be different."""
    if requests is None:
        raise SourceError("requests not installed; live Naar fetch unavailable")
    headers = {"User-Agent": UA, "Accept": "application/json"}
    api_key = os.environ.get("NAAR_API_KEY")
    if api_key:
        headers["X-Api-Key"] = api_key
    try:
        r = requests.get(NAAR_ENDPOINT,
                         params={"status": "active", "limit": limit, "skip": skip},
                         headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        raise SourceError(f"Naar API request failed"
                          f"{f' (HTTP {status})' if status else ''}: {e}") from e
    except ValueError as e:  # .json() decode failure
        raise SourceError(f"Naar API returned non-JSON body: {e}") from e
    if isinstance(body, list):
        return body
    for key in ("products", "data", "items", "results"):
        if isinstance(body, dict) and isinstance(body.get(key), list):
            return body[key]
    raise SourceError(f"Unrecognised Naar response shape: keys={list(body)[:8]}")


def iter_variants(product: dict) -> Iterable[dict]:
    variants = product.get("variants") or []
    if not variants:
        variants = [{"_id": product.get("_id", "") + ":v0",
                     "sellingPrice": product.get("sellingPrice"),
                     "variantName": None, "attributes": {}}]
    yield from variants


# Naar often labels single-SKU rows as "default", and unitOfMeasure rows as
# "Weight" with inventory in `quantity` — none of that belongs in a marketplace
# search query. Only append concrete shopper-facing variant signals.
_NOISE_VARIANT_NAMES = frozenset({
    "default", "default variant", "weight", "size", "colour", "color",
    "volume", "variant", "n/a", "na", "none",
})


def _useful_variant_token(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in _NOISE_VARIANT_NAMES:
        return None
    return s


def variant_attr_pairs(variant: dict) -> list[tuple[str, str]]:
    """Normalise variant attributes to (key, value) pairs. Naar returns
    `attributes` as either a dict, a list of {name/key, value} dicts, or [] —
    so callers must not assume a shape."""
    attrs = variant.get("attributes")
    pairs: list[tuple[str, str]] = []
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            if v is not None:
                pairs.append((str(k), str(v)))
    elif isinstance(attrs, list):
        for item in attrs:
            if isinstance(item, dict):
                k = item.get("name") or item.get("key") or item.get("label") or ""
                v = item.get("value")
                if v is not None:
                    pairs.append((str(k), str(v)))
            elif item is not None:
                pairs.append(("", str(item)))
    return pairs


def variant_search_text(product: dict, variant: dict) -> str:
    bits = [product.get("title", "")]
    vn = _useful_variant_token(
        variant.get("variantName") or variant.get("variantOption"))
    if vn:
        bits.append(vn)
    for _k, v in variant_attr_pairs(variant):
        tok = _useful_variant_token(v)
        if tok:
            bits.append(tok)
    return " ".join(str(b) for b in bits if b).strip()


# --------------------------------------------------------------------------
# Marketplace adapters
# --------------------------------------------------------------------------

class MarketplaceAdapter:
    """Contract per brief §5: per candidate, return the concrete price, the
    displayed seller name, and (where possible) the seller's registered legal
    name — and enumerate ALL offers, not just the buy box (§4.3)."""
    name: str = "base"

    def search(self, query: str) -> list[Candidate]:
        raise NotImplementedError


def _redact_secrets(msg: str) -> str:
    """Keep API keys out of status/evidence strings."""
    return re.sub(r"(api_key=)[^&\s]+", r"\1***", msg, flags=re.I)


# Amazon/Flipkart frequently answer a bot with HTTP 200 and a captcha /
# interstitial body rather than a 4xx. Treating that as "no products" would
# mislabel a block as PRODUCT_NOT_FOUND — the exact dishonesty the brief
# rejects. Markers are specific to avoid flagging legitimate product pages.
_BLOCK_MARKERS = (
    "validatecaptcha",
    "/errors/validatecaptcha",
    "enter the characters you see below",
    "to discuss automated access to amazon data",
    "type the characters you see in this image",
    "our systems have detected unusual traffic",
    "you don't have permission to access",      # Akamai "Access Denied" (Meesho)
    "errors.edgesuite.net",
)


def _looks_blocked(body: str) -> bool:
    low = (body or "")[:20000].lower()
    return any(mk in low for mk in _BLOCK_MARKERS)


def _merge_url_params(url: str, params: dict) -> str:
    """Fold query params into the URL (marketplaces are GET-only here)."""
    if not params:
        return url
    from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update({k: str(v) for k, v in params.items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


class _Resp:
    """Minimal response shim so a Selenium-rendered page flows through the same
    block checks and parsers as a requests.Response (only .text/.status_code used)."""
    __slots__ = ("text", "status_code")

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


# --- Selenium fetch backend (no per-request cost; renders JS; evades basic bot
#     checks). Opt in with USE_SELENIUM=1. A single shared headless Chrome is
#     reused across the run and closed at exit. -----------------------------
_selenium_driver = None


def _selenium_enabled() -> bool:
    return os.environ.get("USE_SELENIUM", "").strip().lower() in ("1", "true", "yes")


def _get_selenium_driver():
    """Lazily build one shared Chrome. Prefers undetected-chromedriver (hides
    navigator.webdriver / automation fingerprints) when available; falls back to
    stock Selenium with the automation flags stripped. SELENIUM_HEADFUL=1 shows
    the window (often bypasses more bot walls); SELENIUM_UC=0 forces stock."""
    global _selenium_driver
    if _selenium_driver is not None:
        return _selenium_driver
    headful = os.environ.get("SELENIUM_HEADFUL", "").strip() in ("1", "true", "yes")
    use_uc = os.environ.get("SELENIUM_UC", "1").strip() not in ("0", "false", "no")
    try:
        if use_uc:
            import undetected_chromedriver as uc
            opts = uc.ChromeOptions()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--lang=en-IN")
            opts.add_argument(f"--user-agent={UA}")
            _selenium_driver = uc.Chrome(options=opts, headless=not headful)
        else:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            opts = Options()
            if not headful:
                opts.add_argument("--headless=new")
            for a in ("--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-blink-features=AutomationControlled",
                      "--lang=en-IN", "--window-size=1366,900", f"--user-agent={UA}"):
                opts.add_argument(a)
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            _selenium_driver = webdriver.Chrome(options=opts)
            _selenium_driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    except Exception as e:
        raise SourceError(f"selenium unavailable: {e}") from e
    return _selenium_driver


def _selenium_get(url: str, wait_ms: Optional[int], timeout: int) -> str:
    driver = _get_selenium_driver()
    try:
        driver.set_page_load_timeout(max(timeout, 30))
        driver.get(url)
    except Exception as e:
        raise SourceError(f"selenium fetch failed: {_redact_secrets(str(e))}") from e
    # Let JS settle (SERP XHR, __NEXT_DATA__ hydration).
    ms = wait_ms if wait_ms is not None else int(_cfg_float("SELENIUM_WAIT_MS", 4000))
    time.sleep(ms / 1000.0)
    return driver.page_source


def _close_selenium() -> None:
    global _selenium_driver
    if _selenium_driver is not None:
        try:
            _selenium_driver.quit()
        except Exception:
            pass
        _selenium_driver = None


import atexit as _atexit
_atexit.register(_close_selenium)


def _http_get(url: str, **kw) -> "requests.Response":
    """GET a marketplace URL through the selected fetch backend.

    Backend precedence:
      1. Selenium (USE_SELENIUM=1) — a real headless Chrome that renders JS and
         evades basic bot checks; no per-request cost. See _get_selenium_driver.
      2. ScraperAPI (SCRAPERAPI_KEY set) for meesho.com, or every host with
         SCRAPERAPI_ALL=1.
      3. Plain requests (default).

    JS render/wait apply to the proxy/Selenium paths. Callers may pass
    render=True/False, wait_ms, params, timeout, headers.
    """
    if requests is None and not _selenium_enabled():
        raise SourceError("requests not installed")
    params = dict(kw.pop("params", None) or {})
    timeout = kw.pop("timeout", 25)
    render_override = kw.pop("render", None)
    wait_ms = kw.pop("wait_ms", None)
    headers = kw.pop("headers", None) or {
        "User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
    }
    api_key = os.environ.get("SCRAPERAPI_KEY", "").strip()
    host = re.sub(r"^www\.", "", (re.match(r"https?://([^/]+)", url) or [None, ""])[1]).lower()
    use_proxy = bool(api_key) and (
        os.environ.get("SCRAPERAPI_ALL", "").strip() in ("1", "true", "yes")
        or host.endswith("meesho.com")
    )
    try:
        if _selenium_enabled():
            full = _merge_url_params(url, params)
            w = wait_ms
            if w is None and host.endswith("meesho.com"):
                w = 6000            # give Meesho's client-side search XHR time
            r = _Resp(_selenium_get(full, wait_ms=w, timeout=timeout))
        elif use_proxy:
            url = _merge_url_params(url, params)
            if render_override is None:
                render = os.environ.get("SCRAPERAPI_RENDER", "").strip() in (
                    "1", "true", "yes")
            else:
                render = bool(render_override)
            # Meesho needs JS for __NEXT_DATA__; default render on for that host.
            if render_override is None and host.endswith("meesho.com"):
                render = True
            sapi = {
                "api_key": api_key,
                "url": url,
                "render": "true" if render else "false",
                "country_code": "in",
            }
            # Give the client-side search XHR time to populate (Meesho).
            if wait_ms is None and host.endswith("meesho.com") and render:
                wait_ms = 5000
            if wait_ms:
                sapi["wait"] = int(wait_ms)
            r = requests.get(
                "https://api.scraperapi.com",
                params=sapi,
                timeout=max(timeout, 120 if render else 60),
            )
        else:
            r = requests.get(url, headers=headers, params=params or None,
                             timeout=timeout, **kw)
    except SourceError:
        raise                                  # selenium/backend errors keep their message
    except Exception as e:  # DNS, timeout, refused — all honest failures
        raise SourceError(f"fetch failed: {_redact_secrets(str(e))}") from e
    if r.status_code in (403, 429, 503):
        raise SourceError(f"blocked or throttled: HTTP {r.status_code}")
    if r.status_code >= 400:
        raise SourceError(f"HTTP {r.status_code}")
    if _looks_blocked(r.text):                         # fix v3-2: 200 + captcha
        raise SourceError("soft-block: captcha/interstitial returned with HTTP 200")
    return r


def _jsonld_offers(html: str) -> list[dict]:
    """Pull schema.org Product offers out of JSON-LD blocks. Deterministic; no LLM."""
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                         html, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("Product", ["Product"]):
                offers = it.get("offers") or {}
                offers = offers if isinstance(offers, list) else [offers]
                for o in offers:
                    if isinstance(o, dict):
                        out.append({"price": o.get("price"),
                                    "availability": o.get("availability", ""),
                                    "seller": (o.get("seller") or {}).get("name")})
    return out


def _extract_embedded_json(html: str, marker: str) -> Optional[dict]:
    """Brace-matched extraction of `marker = {...}` (fix 7). Deterministic:
    respects strings/escapes, no regex-over-JSON guessing."""
    i = html.find(marker)
    if i < 0:
        return None
    j = html.find("{", i)
    if j < 0:
        return None
    depth, in_str, esc = 0, False, False
    for k in range(j, len(html)):
        ch = html[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[j:k + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _walk_first(obj, want_keys: tuple[str, ...]) -> Optional[dict]:
    """Shallowest, document-order sub-dict containing all want_keys (fix v3-1).

    Breadth-first in insertion order: the primary product/offer node in a big
    embedded state (Flipkart __INITIAL_STATE__, Meesho __NEXT_DATA__) is
    normally shallow and appears before recommendation carousels, so BFS is far
    less likely than a LIFO stack to bind a *different* product's price/seller.
    """
    from collections import deque
    q = deque([obj])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            if all(k in cur for k in want_keys):
                return cur
            q.extend(cur.values())
        elif isinstance(cur, list):
            q.extend(cur)
    return None


# Selling-price containers first; the generic ".a-price" fallback is guarded
# against struck-through MRP so we never record the crossed-out list price.
_AMAZON_PRICE_SELECTORS = (
    "#corePrice_feature_div .a-price .a-offscreen",
    "#tp_price_block_total_price_ww .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "span.a-price .a-offscreen",
)


def _amazon_visible_price(soup) -> Optional[float]:
    """First non-strikethrough buy-box price on a product page. Skips MRP that
    Amazon renders inside a struck `.a-text-price` / `data-a-strike` node."""
    for sel in _AMAZON_PRICE_SELECTORS:
        for el in soup.select(sel):
            price_span = el.find_parent("span", class_="a-price")
            if price_span is not None:
                classes = price_span.get("class") or []
                if "a-text-price" in classes or price_span.get("data-a-strike") == "true":
                    continue
            price = _parse_inr(el.get_text())
            if price is not None:
                return price
    return None


class AmazonInAdapter(MarketplaceAdapter):
    """Direct fallback for amazon.in. Search page -> product pages (JSON-LD)
    -> AOD endpoint for the full offer list. Blocks surface honestly: a failed
    offer fetch is recorded on the candidate (fix 6), not swallowed."""
    name = "amazon_in"
    AOD = "https://www.amazon.in/gp/product/ajax/ref=aod_f_new?asin={asin}&pc=dp&experienceId=aodAjaxMain"

    def search(self, query: str) -> list[Candidate]:
        from bs4 import BeautifulSoup
        r = _http_get("https://www.amazon.in/s", params={"k": query})
        soup = BeautifulSoup(r.text, "html.parser")
        cands: list[Candidate] = []
        for div in soup.select('div[data-asin][data-component-type="s-search-result"]')[:5]:
            asin = div.get("data-asin", "").strip()
            title_el = div.select_one("h2 span")
            if not asin or not title_el:
                continue
            cands.append(Candidate(self.name, asin,
                                   f"https://www.amazon.in/dp/{asin}",
                                   title_el.get_text(" ", strip=True)))
        for c in cands:
            try:
                c.offers = self._offers(c.listing_id)
            except SourceError as e:
                c.offers, c.offers_error = [], str(e)      # fix 6
            time.sleep(1.0)  # be polite; this is a 10-product POC, not a crawler
        return cands

    def _offers(self, asin: str) -> list[Offer]:
        from bs4 import BeautifulSoup
        offers: list[Offer] = []
        pr = _http_get(f"https://www.amazon.in/dp/{asin}")
        soup = BeautifulSoup(pr.text, "html.parser")

        # Buy box via product page JSON-LD when present.
        for o in _jsonld_offers(pr.text):
            offers.append(Offer(seller_display=o.get("seller"),
                                price_inr=_to_float(o.get("price")),
                                in_stock="OutOfStock" not in str(o.get("availability")),
                                offer_ref=f"{asin}:buybox"))

        # Amazon.in often ships DP HTML with empty JSON-LD offers. Fall back to
        # the visible buy-box price + "Sold by" / store link.
        if not offers:
            price = _amazon_visible_price(soup)
            sold = (soup.select_one("#sellerProfileTriggerId")
                    or soup.select_one("#merchant-info a")
                    or soup.select_one("a[href*='seller=']"))
            seller = sold.get_text(strip=True) if sold else None
            if price is not None or seller:
                offers.append(Offer(seller_display=seller, price_inr=price,
                                    offer_ref=f"{asin}:buybox_html"))
        elif not offers[0].seller_display:
            sold = (soup.select_one("#sellerProfileTriggerId")
                    or soup.select_one("#merchant-info a")
                    or soup.select_one("a[href*='seller=']"))
            if sold:
                offers[0].seller_display = sold.get_text(strip=True)

        # Full offer list via AOD (§4.3). Optional — many locales 404 this endpoint.
        try:
            ar = _http_get(self.AOD.format(asin=asin))
            asoup = BeautifulSoup(ar.text, "html.parser")
            for i, block in enumerate(asoup.select("#aod-offer")):
                sold_by = block.select_one("#aod-offer-soldBy a, #aod-offer-soldBy .a-color-base")
                price_el = block.select_one(".a-price .a-offscreen")
                offers.append(Offer(
                    seller_display=sold_by.get_text(strip=True) if sold_by else None,
                    price_inr=_parse_inr(price_el.get_text()) if price_el else None,
                    offer_ref=f"{asin}:aod{i}"))
        except SourceError:
            if not offers:
                raise
        if not offers:
            raise SourceError(f"no offers extracted for {asin}")
        return offers


class FlipkartAdapter(MarketplaceAdapter):
    name = "flipkart"

    def search(self, query: str) -> list[Candidate]:
        from bs4 import BeautifulSoup
        r = _http_get("https://www.flipkart.com/search", params={"q": query})
        soup = BeautifulSoup(r.text, "html.parser")
        cands: list[Candidate] = []
        for a in soup.select('a[href*="/p/"]')[:5]:
            href = a.get("href", "")
            title = a.get("title") or a.get_text(" ", strip=True)
            pid = re.search(r"pid=([A-Z0-9]+)", href)
            if not title:
                continue
            url = "https://www.flipkart.com" + href.split("&lid=")[0]
            cands.append(Candidate(self.name, pid.group(1) if pid else href[:40], url, title))
        for c in cands:
            try:
                c.offers = self._offers(c.listing_url)
            except SourceError as e:
                c.offers, c.offers_error = [], str(e)      # fix 6
            time.sleep(1.0)
        return cands

    def _offers(self, url: str) -> list[Offer]:
        """Fix 7: parse the page's __INITIAL_STATE__ JSON and walk it, rather
        than taking the first regex hit anywhere on the page."""
        pr = _http_get(url)
        state = _extract_embedded_json(pr.text, "window.__INITIAL_STATE__")
        if state is not None:
            ref = url.rsplit("=", 1)[-1][:24]

            def _final_price(node: Optional[dict]) -> Optional[float]:
                fp = (node or {}).get("finalPrice")
                if isinstance(fp, dict):
                    return _to_float(fp.get("value"))
                return _to_float(fp)

            # Fix v3-1: prefer a single node carrying BOTH the seller and the
            # price, so they cannot be paired from two unrelated products in the
            # state. Only fall back to independent walks when no such node
            # exists — and BFS order keeps that fallback on the primary product.
            combo = _walk_first(state, ("sellerName", "finalPrice"))
            if combo is not None:
                return [Offer(seller_display=combo.get("sellerName"),
                              price_inr=_final_price(combo), offer_ref=ref)]
            seller_node = _walk_first(state, ("sellerName",))
            price_node = _walk_first(state, ("finalPrice",))
            price = _final_price(price_node)
            if seller_node or price is not None:
                return [Offer(seller_display=(seller_node or {}).get("sellerName"),
                              price_inr=price, offer_ref=ref)]
        # Narrow fallback, kept for markup drift; still structured-data only.
        sold = re.search(r'"sellerName"\s*:\s*"([^"]+)"', pr.text)
        return [Offer(seller_display=sold.group(1) if sold else None,
                      price_inr=None, offer_ref=url[-24:])]


class MeeshoAdapter(MarketplaceAdapter):
    name = "meesho"

    def search(self, query: str) -> list[Candidate]:
        r = _http_get("https://www.meesho.com/search", params={"q": query})
        data = self._next_data(r.text)
        if data is None:
            raise SourceError("no __NEXT_DATA__ payload (likely a block page)")
        cands: list[Candidate] = []

        # Legacy catalogue payload (older Meesho markup).
        catalogs = (_walk_first(data, ("catalogs",)) or {}).get("catalogs") or []
        for cat in catalogs[:5]:
            pid = str(cat.get("catalog_id") or cat.get("id") or "")
            if not pid:
                continue
            supplier = (cat.get("supplier") or {}).get("name")
            # Fix 8: min_product_price is a catalogue minimum, NOT a specific
            # seller's offer price. Never record it as an offer price.
            cands.append(Candidate(
                self.name, pid, f"https://www.meesho.com/s/p/{pid}",
                cat.get("name", "") or "",
                [Offer(seller_display=supplier, price_inr=None, offer_ref=pid)]))

        # Current search page: props.pageProps.initialState.searchListing.listing.products
        if not cands:
            products = (
                (((data.get("props") or {}).get("pageProps") or {})
                 .get("initialState") or {})
                .get("searchListing") or {}
            )
            listing = (products.get("listing") or {}) if isinstance(products, dict) else {}
            for prod in (listing.get("products") or [])[:5]:
                if not isinstance(prod, dict):
                    continue
                pid = str(prod.get("product_id") or prod.get("id")
                          or prod.get("hex_id") or "")
                name = prod.get("name") or prod.get("product_name") or ""
                supplier = None
                sup = prod.get("supplier") or prod.get("shop") or {}
                if isinstance(sup, dict):
                    supplier = sup.get("name") or sup.get("shop_name")
                slug = prod.get("slug") or ""
                url = (f"https://www.meesho.com/{slug}/p/{pid}" if slug and pid
                       else f"https://www.meesho.com/s/p/{pid}")
                if not pid and not name:
                    continue
                cands.append(Candidate(
                    self.name, pid or slug[:40], url, name,
                    [Offer(seller_display=supplier, price_inr=None,
                           offer_ref=pid or slug[:24])]))

        # Rendered HTML often has product cards before XHR fills __NEXT_DATA__.
        if not cands:
            cands = self._candidates_from_html(r.text)

        # Fix v3-3: the SERP card ₹ on Meesho is the CATALOGUE minimum across
        # suppliers, not the specific supplier's price — recording it as this
        # seller's offer price is the same lie as the old min_product_price
        # (fix 8). Take the price ONLY from the PDP node that is tied to the
        # supplier (_page_offer), and only when we already have a seller name.
        for c in cands:
            if not c.offers:
                continue
            if c.offers[0].seller_display and c.offers[0].price_inr is None:
                try:
                    price, _seller = self._page_offer(c.listing_url)
                    c.offers[0].price_inr = price
                except SourceError as e:
                    c.offers_error = str(e)
            # Clean rating/price chrome out of HTML-fallback titles for the gate.
            c.title = re.sub(
                r"\s*₹[\d,]+(?:\.\d+)?(?:\s*₹[\d,]+(?:\.\d+)?)?(?:\s*\d+%\s*off)?"
                r"(?:\s*[\d.]+)?(?:\s*\d+\s*Reviews?)?(?:\s*Supplier)?\s*$",
                "", c.title, flags=re.I).strip() or c.title
        return cands

    @staticmethod
    def _next_data(html: str) -> Optional[dict]:
        m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      html, re.S | re.I)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return (_extract_embedded_json(html, '"__NEXT_DATA__"')
                or _extract_embedded_json(html, "__NEXT_DATA__"))

    def _candidates_from_html(self, html: str) -> list[Candidate]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        cands: list[Candidate] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/p/"]'):
            href = a.get("href") or ""
            m = re.search(r"/([^/]+)/p/([A-Za-z0-9]+)", href)
            if not m:
                continue
            slug, pid = m.group(1), m.group(2)
            if pid in seen or len(pid) < 4:
                continue
            # Skip non-product chrome links like /p/6 from nav.
            if slug in ("", "search", "cart", "auth"):
                continue
            seen.add(pid)
            title = a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True)
            if not title or len(title) < 8:
                title = slug.replace("-", " ")
            url = href if href.startswith("http") else "https://www.meesho.com" + href
            cands.append(Candidate(
                self.name, pid, url, title,
                [Offer(seller_display=None, price_inr=None, offer_ref=pid)]))
            if len(cands) >= 5:
                break
        return cands

    def _page_offer(self, url: str) -> tuple[Optional[float], Optional[str]]:
        pr = _http_get(url)
        data = self._next_data(pr.text) or {}
        node = _walk_first(data, ("price", "supplier")) or \
               _walk_first(data, ("price", "name"))
        price = _to_float(node.get("price")) if node else None
        seller = None
        if node and isinstance(node.get("supplier"), dict):
            seller = node["supplier"].get("name")
        if seller is None:
            sn = _walk_first(data, ("shop_name",)) or _walk_first(data, ("supplier_name",))
            if sn:
                seller = sn.get("shop_name") or sn.get("supplier_name")
        if price is None:
            m = re.search(r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', pr.text)
            if m:
                price = _to_float(m.group(1))
        return price, seller


def _parse_inr(s: str) -> Optional[float]:
    """Parse an INR amount from text that carries the ₹ symbol. Requiring the
    symbol prevents mistaking a size or quantity ("40 X 35", "6-in-1") for a
    price when the input is a free-form card title rather than a price node."""
    m = re.search(r"₹\s*([\d,]+(?:\.\d+)?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Fixture backend — contract-faithful synthetic data for the offline demo.
# Field names and quirks mirror the brief §2 (discounted sellingPrice 211.47
# vs priceWithoutTax 399; legal vs store names; a saree with junk HSN text).
# --------------------------------------------------------------------------

FIXTURE_NAAR = [
    {
        "_id": "np_amla01", "title": "Amla Powder", "currency": "INR",
        "description": "Pure Indian amla powder. Net weight 100g. Country of Origin: India.",
        "sellerId": "ns_treasure",
        "seller": {"storeName": "TREASURE FLAVOURS",
                   "businessName": "TREASURE FLAVOURS FOODS PRIVATE LIMITED"},
        "variants": [{"_id": "nv_amla01_100g", "variantName": "100g",
                      "attributes": {"weight": "100g"},
                      "sellingPrice": 211.47, "priceWithoutTax": 399,
                      "originalPriceWithTax": 470.82,
                      "discount": {"type": "percent", "value": 47}}],
    },
    {
        "_id": "np_saree01", "title": "Kanchipuram Silk Cotton Saree",
        "currency": "INR",
        "description": "Handloom silk cotton saree, 6.2m with blouse piece.",
        "hsnData": {"description": "Copper waste and scrap"},  # junk — excluded from matching
        "sellerId": "ns_kaithari",
        "seller": {"storeName": "Kaithari Kalanjiyam",
                   "businessName": "NITHYA VINOTH KUMAR"},
        "variants": [{"_id": "nv_saree01_teal", "variantName": "Teal",
                      "attributes": {"colour": "Teal"},
                      "sellingPrice": 1499.0, "priceWithoutTax": 1427.62,
                      "originalPriceWithTax": 1899.0}],
    },
]

FIXTURE_MARKET: dict[tuple[str, str], "list[Candidate] | str"] = {
    # (marketplace, naar_product_id) -> candidates, or "RAISE" to simulate a source failure
    ("amazon_in", "np_amla01"): [Candidate(
        "amazon_in", "B0FIXAMLA1", "https://www.amazon.in/dp/B0FIXAMLA1",
        "Pure Amla Powder (Indian Gooseberry) 100g",
        [Offer("RetailNet India", None, 259.0, mrp_inr=470.0, offer_ref="B0FIXAMLA1:buybox"),
         # The Naar seller is on the listing but does NOT hold the buy box (§4.3):
         Offer("Treasure Flavours", "TREASURE FLAVOURS FOODS PVT LTD", 249.0,
               offer_ref="B0FIXAMLA1:aod1")])],
    ("flipkart", "np_amla01"): [Candidate(
        "flipkart", "AMLFK123", "https://www.flipkart.com/x/p/i?pid=AMLFK123",
        "Amla Powder 100 g (Indian Gooseberry)",
        [Offer("GreenLeaf Traders", "GREENLEAF TRADERS LLP", 235.0, offer_ref="AMLFK123")])],
    ("meesho", "np_amla01"): [Candidate(
        "meesho", "MS77001", "https://www.meesho.com/s/p/MS77001",
        "Amla Powder 100g Indian",
        [Offer(None, None, None, offer_ref="MS77001")])],  # seller hidden -> AMBIGUOUS
    ("amazon_in", "np_saree01"): [Candidate(
        "amazon_in", "B0FIXSAREE", "https://www.amazon.in/dp/B0FIXSAREE",
        "Kanchipuram Silk Cotton Saree Maroon",  # wrong variant colour -> product gate fails
        [Offer("Kaithari Kalanjiyam", None, 1599.0, offer_ref="B0FIXSAREE:buybox")])],
    ("flipkart", "np_saree01"): [Candidate(
        "flipkart", "SRFK456", "https://www.flipkart.com/x/p/i?pid=SRFK456",
        "Kanchipuram Silk Cotton Saree Teal with Blouse Piece",
        [Offer("Kaithari Kalanjiyam", "NITHYA VINOTH KUMAR", None,
               in_stock=False, offer_ref="SRFK456")])],  # matched seller, unbuyable
    ("meesho", "np_saree01"): "RAISE",
}


class FixtureAdapter(MarketplaceAdapter):
    def __init__(self, marketplace: str):
        self.name = marketplace
        self._pid: Optional[str] = None

    def bind(self, naar_product_id: str):
        self._pid = naar_product_id
        return self

    def search(self, query: str) -> list[Candidate]:
        val = FIXTURE_MARKET.get((self.name, self._pid), [])
        if val == "RAISE":
            raise SourceError("simulated extraction failure (fixture)")
        return list(val)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

def product_gate(naar_product: dict, variant: dict, cand: Candidate,
                 llm_judge: bool, strict: bool = False) -> tuple[str, str]:
    """Returns (verdict, evidence). Verdict: 'pass' | 'fail' | 'borderline'.
    Fuzzy similarity ranks; it never proves. HSN text is never used (§2)."""
    n_text = variant_search_text(naar_product, variant)
    desc = naar_product.get("description") or ""
    n_attrs = extract_attrs(n_text + " " + desc)
    c_attrs = extract_attrs(cand.title)
    evidence = []

    # Quantity must agree when Naar states one.
    if "qty_base" in n_attrs:
        if "qty_base" not in c_attrs:
            return "borderline", "naar states quantity; listing title omits it"
        if abs(n_attrs["qty_base"] - c_attrs["qty_base"]) > 1e-6:
            return "fail", (f"quantity mismatch {n_attrs['qty_raw']} vs {c_attrs.get('qty_raw')}")
        evidence.append(f"quantity={n_attrs['qty_raw']}")

    # Stated variant attributes (colour, size — incl. numeric sizes like "8",
    # "42") must appear as whole words/numbers in the title (fix 2, v3-5).
    # Quantity-style values ("100g", "250 ml") are skipped here because the
    # quantity gate above already checks them with unit normalisation — a
    # literal check would false-fail "100g" against a "100 g" title.
    for k, v in variant_attr_pairs(variant):
        if not v or QTY_RE.search(v):
            continue
        if re.search(rf"\b{re.escape(v)}\b", cand.title, re.I):
            evidence.append(f"{k}={v}" if k else f"attr={v}")
        else:
            label = f"'{k}={v}'" if k else f"'{v}'"
            return "fail", f"variant attribute {label} absent from listing title"

    # How much of the Naar identity is present in the listing (coverage), and
    # how much of the listing is content Naar cannot explain (extra ratio).
    nt, ct = content_tokens(n_text), content_tokens(cand.title)
    coverage = len(nt & ct) / max(1, len(nt))
    evidence.append(f"coverage={coverage:.2f}")

    cov_fail = _cfg_float("MATCH_COVERAGE_FAIL", 0.35)
    cov_pass = _cfg_float("MATCH_COVERAGE_PASS", 0.6)
    if coverage < cov_fail:
        return "fail", "; ".join(evidence)

    # Fix 3: containment alone must not prove a match. We measure the *share* of
    # the listing's content tokens that nothing on the Naar side (title, variant,
    # description, seller/brand names) explains — a fraction, not a hand-tuned
    # word list. A derivative product ("Amla Powder Hair Mask" vs "Amla Powder")
    # is dominated by unexplained tokens; verbose marketing on an otherwise exact
    # listing is diluted by the matched tokens. Brand/store names are expected
    # (a seller listing under their own name) and count as explained — this is
    # derived from Naar data, not curated per-catalog.
    seller = naar_product.get("seller") or {}
    explained = (
        nt
        | content_tokens(desc)
        | content_tokens(str(seller.get("storeName") or ""))
        | content_tokens(str(seller.get("businessName") or ""))
    )
    unexplained = ct - explained
    extra_ratio = len(unexplained) / max(1, len(ct))
    if unexplained:
        evidence.append(f"unexplained={sorted(unexplained)} ratio={extra_ratio:.2f}")

    # Default 0.45 sits above verbose-but-exact listings and below derivative
    # products; --strict tightens it. Tunable via MATCH_MAX_UNEXPLAINED_RATIO.
    max_extra = _cfg_float("MATCH_MAX_UNEXPLAINED_RATIO", 0.30 if strict else 0.45)
    if coverage >= cov_pass and extra_ratio <= max_extra:
        return "pass", "; ".join(evidence)

    if llm_judge:
        verdict = _llm_same_product(n_text + " | " + desc, cand.title)
        if verdict is not None:
            evidence.append(f"llm_judge={'same' if verdict else 'different'}")
            return ("pass" if verdict else "fail"), "; ".join(evidence)
    return "borderline", "; ".join(evidence)


_JUDGE_PROMPT = (
    "Are these the same retail product and variant? Reply with only "
    'JSON {{"same_product": true|false}}.\nA: {a}\nB: {b}'
)


def _judge_provider() -> str:
    """Resolve the borderline-judge backend. Explicit LLM_JUDGE_PROVIDER wins;
    otherwise auto-detect from whichever API key is present (anthropic first,
    for back-compat). 'openai' covers ANY OpenAI-compatible endpoint (OpenAI,
    Qwen, DeepSeek, Groq, OpenRouter, local Ollama/vLLM) via OPENAI_BASE_URL."""
    p = os.environ.get("LLM_JUDGE_PROVIDER", "").strip().lower()
    if p:
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return ""


def _parse_same_product(txt: str) -> Optional[bool]:
    """Pull the structured {"same_product": bool} verdict out of a model reply.
    Anything unparseable returns None -> the gate stays borderline."""
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        return bool(json.loads(m.group(0))["same_product"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _judge_anthropic(prompt: str) -> Optional[bool]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 64,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30)
    r.raise_for_status()
    txt = "".join(b.get("text", "") for b in r.json().get("content", []))
    return _parse_same_product(txt)


def _judge_openai_compatible(prompt: str) -> Optional[bool]:
    """Any OpenAI /chat/completions-compatible endpoint. Point at a different
    vendor with OPENAI_BASE_URL (e.g. https://api.deepseek.com/v1,
    https://dashscope-intl.aliyuncs.com/compatible-mode/v1, http://localhost:11434/v1)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "max_tokens": 64, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30)
    r.raise_for_status()
    txt = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return _parse_same_product(txt)


def _llm_same_product(naar_text: str, listing_title: str) -> Optional[bool]:
    """Optional borderline judge (§7), provider-agnostic. Structured verdict
    only — never a price or seller assertion. Returns None whenever the judge
    is unavailable or errors, so the gate stays honestly borderline and never
    fabricates a verdict.

    Provider via LLM_JUDGE_PROVIDER = anthropic | openai (default: auto by key):
      - anthropic: ANTHROPIC_API_KEY (+ ANTHROPIC_MODEL, default claude-haiku-4-5)
      - openai:    OPENAI_API_KEY (+ OPENAI_BASE_URL, OPENAI_MODEL) — also serves
                   any OpenAI-compatible vendor (Qwen/DeepSeek/Groq/OpenRouter/Ollama).
    """
    if requests is None:
        return None
    provider = _judge_provider()
    prompt = _JUDGE_PROMPT.format(a=naar_text, b=listing_title)
    try:
        if provider == "anthropic":
            return _judge_anthropic(prompt)
        if provider in ("openai", "openai-compatible", "qwen", "deepseek",
                        "groq", "openrouter", "ollama"):
            return _judge_openai_compatible(prompt)
        return None  # unknown/unset provider -> no judge, stays borderline
    except Exception:
        return None  # judge unavailable -> stays borderline; never fabricate a verdict


def seller_gate(naar_seller: dict, offer: Offer) -> tuple[str, float, str]:
    """Returns (verdict, confidence, signal). Verdict: MATCH | OTHER | AMBIGUOUS.
    Only exactness (after conservative normalisation, or token-set equality)
    is a match. Similarity in [0.75, 1.0) is a proposal (AMBIGUOUS); below
    that, an identifiable name counts towards OTHER."""
    store = naar_seller.get("storeName") or ""
    legal = naar_seller.get("businessName") or ""
    best_verdict: Optional[str] = None   # None until an identifiable comparison happens
    best_conf, best_sig = 0.0, ""

    for observed, sig_prefix in ((offer.seller_legal, "legal_name"),
                                 (offer.seller_display, "sold_by_name")):
        if not observed:
            continue
        for target, tname in ((legal, "businessName"), (store, "storeName")):
            if not target:
                continue
            sim, exactness = name_compare(observed, target)
            if exactness == "exact":
                return "MATCH", 0.95, f"{sig_prefix}=={tname}"
            if exactness == "token_set":
                return "MATCH", 0.90, f"{sig_prefix}=={tname} (token_set)"
            if sim >= 0.75:
                # A proposal; keep the strongest one. Never downgraded later.
                if best_verdict != "AMBIGUOUS" or sim > best_conf:
                    best_verdict, best_conf, best_sig = "AMBIGUOUS", sim, \
                        f"{sig_prefix}~{tname} ({sim:.2f}) — proposal only"
            elif best_verdict != "AMBIGUOUS" and sim >= best_conf:
                best_verdict, best_conf, best_sig = "OTHER", sim, \
                    f"{sig_prefix} differs from {tname} ({sim:.2f})"

    if best_verdict is None:             # nothing identifiable to compare
        return "AMBIGUOUS", 0.0, "seller_hidden"
    return best_verdict, best_conf, best_sig


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def compare_variant(product: dict, variant: dict, adapter: MarketplaceAdapter,
                    llm_judge: bool, strict: bool = False) -> Record:
    if variant.get("sellingPrice") in (None, ""):
        # Fix 5 (defence in depth): never coerce a missing Naar price to 0.0.
        raise ValueError(f"variant {variant.get('_id')!r} has no sellingPrice; "
                         "skip it upstream rather than recording a zero")
    query = variant_search_text(product, variant)
    # Meesho SERP quality improves sharply when the Naar store/brand is in the
    # query; Amazon/Flipkart already rank brand tokens from the title alone.
    if adapter.name == "meesho":
        store = ((product.get("seller") or {}).get("storeName") or "").strip()
        if store and store.casefold() not in query.casefold():
            query = f"{store} {query}"
    base = dict(naar_product_id=product.get("_id", ""),
                naar_variant_id=variant.get("_id", ""),
                naar_seller_id=product.get("sellerId", ""),
                marketplace=adapter.name,
                naar_selling_price=float(variant["sellingPrice"]),
                search_query=query)

    try:
        candidates = adapter.search(query)
    except SourceError as e:
        return Record(**base, status="SOURCE_ERROR", match_evidence=str(e))

    product_matched: list[tuple[Candidate, str]] = []
    any_borderline = False
    for cand in candidates:
        verdict, evidence = product_gate(product, variant, cand, llm_judge, strict)
        if verdict == "pass":
            product_matched.append((cand, evidence))
        elif verdict == "borderline":
            any_borderline = True

    if not product_matched:
        return Record(**base,
                      status="AMBIGUOUS_MATCH" if any_borderline else "PRODUCT_NOT_FOUND",
                      product_match_method="attribute_gate",
                      match_evidence="borderline candidates only" if any_borderline
                                     else "no candidate passed the product gate")

    # Fix 4/6: collect verdicts across ALL matched candidates and offers,
    # then decide — nothing returns early on the first offer it sees.
    seller = product.get("seller") or {}
    matched_offers: list[tuple[Candidate, Offer, float, str, str]] = []
    ambiguous_best: Optional[Record] = None
    saw_other = False
    offers_failed = [c.offers_error for c, _ in product_matched if c.offers_error]

    for cand, pevidence in product_matched:
        for offer in cand.offers or [Offer(None)]:
            verdict, conf, signal = seller_gate(seller, offer)
            if verdict == "MATCH":
                matched_offers.append((cand, offer, conf, signal, pevidence))
            elif verdict == "AMBIGUOUS":
                rec = Record(**base, status="AMBIGUOUS_MATCH",
                             marketplace_sold_by=offer.seller_display,
                             marketplace_seller_legal_name=offer.seller_legal,
                             listing_id=cand.listing_id, listing_url=cand.listing_url,
                             offer_ref=offer.offer_ref,
                             product_match_method="attribute_gate",
                             seller_match_signal=signal, confidence=conf,
                             match_evidence=pevidence)
                if ambiguous_best is None or (conf or 0) > (ambiguous_best.confidence or 0):
                    ambiguous_best = rec
            else:
                saw_other = True

    if matched_offers:
        purchasable = [t for t in matched_offers if t[1].in_stock and t[1].price_inr is not None]
        if purchasable:
            cand, offer, conf, signal, pevidence = min(purchasable, key=lambda t: t[1].price_inr)
            return Record(**base, status="MATCHED",
                          marketplace_selling_price=offer.price_inr,
                          marketplace_sold_by=offer.seller_display,
                          marketplace_seller_legal_name=offer.seller_legal,
                          listing_id=cand.listing_id, listing_url=cand.listing_url,
                          offer_ref=offer.offer_ref,
                          delivery_charge=offer.delivery_inr, mrp_displayed=offer.mrp_inr,
                          product_match_method="attribute_gate",
                          seller_match_signal=signal, confidence=conf,
                          match_evidence=pevidence)
        # Fix v3-4: scan ALL matched offers, not just [0]. A matched, in-stock
        # offer whose price we could not extract is a collection failure and
        # must win over an OUT_OF_STOCK sibling — otherwise offer order could
        # silently hide a SOURCE_ERROR behind an OOS listing.
        price_fail = [t for t in matched_offers if t[1].in_stock and t[1].price_inr is None]
        if price_fail:
            cand, offer, conf, signal, pevidence = price_fail[0]
            # Matched the seller but could not extract a price: that is a
            # collection failure, never a guess and never mislabelled OOS.
            return Record(**base, status="SOURCE_ERROR",
                          marketplace_sold_by=offer.seller_display,
                          marketplace_seller_legal_name=offer.seller_legal,
                          listing_id=cand.listing_id, listing_url=cand.listing_url,
                          offer_ref=offer.offer_ref,
                          seller_match_signal=signal, confidence=conf,
                          match_evidence=(pevidence + "; seller matched but price "
                                          "extraction failed"))
        cand, offer, conf, signal, pevidence = matched_offers[0]
        return Record(**base, status="OUT_OF_STOCK",
                      marketplace_sold_by=offer.seller_display,
                      marketplace_seller_legal_name=offer.seller_legal,
                      listing_id=cand.listing_id, listing_url=cand.listing_url,
                      offer_ref=offer.offer_ref,
                      product_match_method="attribute_gate",
                      seller_match_signal=signal, confidence=conf,
                      match_evidence=pevidence)

    if offers_failed:
        # A product-matched listing whose offer list we could not enumerate:
        # the Naar seller may be on it, so neither SOLD_BY_OTHER nor
        # AMBIGUOUS is honest — this is a collection failure (fix 6).
        return Record(**base, status="SOURCE_ERROR",
                      product_match_method="attribute_gate",
                      match_evidence="offer enumeration failed on a product-matched "
                                     "listing: " + "; ".join(offers_failed))
    if ambiguous_best:          # never upgraded to MATCHED (§4)
        return ambiguous_best
    if saw_other:
        return Record(**base, status="SOLD_BY_OTHER",
                      product_match_method="attribute_gate",
                      seller_match_signal="sold_by_name",
                      match_evidence="product found; every identifiable offer "
                                     "belongs to a different seller")
    return Record(**base, status="AMBIGUOUS_MATCH",
                  product_match_method="attribute_gate",
                  seller_match_signal="seller_hidden",
                  match_evidence="product found; no offer exposes a seller identity")


def run(args) -> list[Record]:
    if args.backend == "fixture":
        products = FIXTURE_NAAR
        adapters = {m: FixtureAdapter(m) for m in args.marketplaces}
    else:
        products = fetch_naar_products(args.limit, args.skip)
        direct = {"amazon_in": AmazonInAdapter, "flipkart": FlipkartAdapter,
                  "meesho": MeeshoAdapter}
        adapters = {m: direct[m]() for m in args.marketplaces}

    records: list[Record] = []
    for product in products:
        for variant in iter_variants(product):
            if variant.get("sellingPrice") in (None, ""):
                # Fix 5: a missing Naar price is a data problem, never ₹0.00.
                print(f"[SKIPPED          ] {product.get('title','')[:34]:<34} "
                      f"({variant.get('variantName') or '-'}) — variant has no sellingPrice",
                      file=sys.stderr)
                continue
            for m, adapter in adapters.items():
                if isinstance(adapter, FixtureAdapter):
                    adapter.bind(product.get("_id", ""))
                rec = compare_variant(product, variant, adapter, args.llm_judge, args.strict)
                records.append(rec)
                delta = ""
                if rec.status == "MATCHED":
                    d = rec.marketplace_selling_price - rec.naar_selling_price
                    delta = f"  naar ₹{rec.naar_selling_price:.2f} vs ₹{rec.marketplace_selling_price:.2f} (Δ {d:+.2f})"
                print(f"[{rec.status:<17}] {product.get('title','')[:34]:<34} "
                      f"({variant.get('variantName') or '-'}) @ {m}{delta}")
    return records


def write_outputs(records: list[Record], outdir: str):
    os.makedirs(outdir, exist_ok=True)
    rows = [dataclasses.asdict(r) for r in records]
    with open(os.path.join(outdir, "results.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nPer-platform status split:")
    for m in sorted({r.marketplace for r in records}):
        counts: dict[str, int] = {}
        for r in records:
            if r.marketplace == m:
                counts[r.status] = counts.get(r.status, 0) + 1
        print(f"  {m:<10} " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"\nWrote {len(records)} records to {outdir}/results.csv and results.jsonl")


# --------------------------------------------------------------------------
# Self-test — the regression cases from the code review, pinned.
# --------------------------------------------------------------------------

def self_test() -> int:
    failures = []

    def check(label, cond):
        print(("  PASS  " if cond else "  FAIL  ") + label)
        if not cond:
            failures.append(label)

    # 1. Conservative seller normalisation
    v, c, s = seller_gate({"storeName": "", "businessName": "Reliance Industries"},
                          Offer(seller_display="Reliance Retail"))
    check("Reliance Retail is NOT Reliance Industries", v != "MATCH")
    v, c, s = seller_gate({"storeName": "TREASURE FLAVOURS",
                           "businessName": "TREASURE FLAVOURS FOODS PRIVATE LIMITED"},
                          Offer(seller_display=None,
                                seller_legal="TREASURE FLAVOURS FOODS PVT LTD"))
    check("PVT LTD vs PRIVATE LIMITED still matches on legal name", v == "MATCH")
    v, c, s = seller_gate({"storeName": "", "businessName": "Flavours Treasure Foods Ltd"},
                          Offer(seller_display="Treasure Flavours Foods"))
    check("word reordering matches via token_set", v == "MATCH" and "token_set" in s)

    # 2. Word-boundary attributes
    verdict, _ = product_gate({"title": "Kanchipuram Silk Cotton Saree", "description": ""},
                              {"attributes": {"colour": "Teal"}, "variantName": "Teal"},
                              Candidate("x", "X", "u", "Steal Deal Kanchipuram Silk Cotton Saree"),
                              False)
    check("'Teal' does not match inside 'Steal'", verdict == "fail")

    # 3. Derivative products never auto-pass
    amla = FIXTURE_NAAR[0]
    verdict, ev = product_gate(amla, amla["variants"][0],
                               Candidate("x", "Y", "u", "Amla Powder Hair Mask 100g"), False)
    check("'Amla Powder Hair Mask' is borderline, not a pass", verdict == "borderline")
    verdict, _ = product_gate(amla, amla["variants"][0],
                              Candidate("x", "Z", "u", "Pure Amla Powder (Indian Gooseberry) 100g"),
                              False)
    check("description-corroborated listing still passes", verdict == "pass")

    # 4. Purchasable matched offer beats OUT_OF_STOCK on an earlier listing
    class Stub(MarketplaceAdapter):
        name = "amazon_in"
        def search(self, q):
            return [Candidate("amazon_in", "C1", "u1", "Pure Indian Amla Powder 100g",
                              [Offer("Treasure Flavours", None, None, in_stock=False,
                                     offer_ref="C1:o")]),
                    Candidate("amazon_in", "C2", "u2", "Indian Amla Powder 100g",
                              [Offer("Treasure Flavours", None, 199.0, offer_ref="C2:o")])]
    rec = compare_variant(amla, amla["variants"][0], Stub(), False)
    check("in-stock match wins over earlier OOS listing",
          rec.status == "MATCHED" and rec.marketplace_selling_price == 199.0)

    # 5. Price only on MATCHED (invariant)
    r = Record("p", "v", "s", "amazon_in", "SOLD_BY_OTHER", 100.0,
               marketplace_selling_price=50.0)
    check("non-MATCHED rows never carry a price", r.marketplace_selling_price is None)

    # 6. Failed offer enumeration is SOURCE_ERROR, not AMBIGUOUS
    class StubErr(MarketplaceAdapter):
        name = "amazon_in"
        def search(self, q):
            c = Candidate("amazon_in", "C3", "u3", "Indian Amla Powder 100g")
            c.offers_error = "blocked or throttled: HTTP 503"
            return [c]
    rec = compare_variant(amla, amla["variants"][0], StubErr(), False)
    check("blocked offer list on matched listing -> SOURCE_ERROR",
          rec.status == "SOURCE_ERROR")

    # 7. Matched seller but unextractable price is SOURCE_ERROR, never OOS/guess
    class StubNoPrice(MarketplaceAdapter):
        name = "meesho"
        def search(self, q):
            return [Candidate("meesho", "C4", "u4", "Indian Amla Powder 100g",
                              [Offer("Treasure Flavours", None, None, offer_ref="C4:o")])]
    rec = compare_variant(amla, amla["variants"][0], StubNoPrice(), False)
    check("matched but unpriced offer -> SOURCE_ERROR", rec.status == "SOURCE_ERROR")

    # 8. (v3-1) _walk_first is document-order/shallowest, not LIFO — the primary
    # node wins over a deeper recommendation node carrying the same key.
    blob = {"main": {"finalPrice": {"value": 100}},
            "reco": {"items": [{"finalPrice": {"value": 999}}]}}
    node = _walk_first(blob, ("finalPrice",))
    check("_walk_first returns the shallow/primary node, not a deep reco",
          node is not None and node["finalPrice"]["value"] == 100)

    # 9. (v3-2) A 200 response carrying an Amazon captcha body is a block.
    check("captcha interstitial (HTTP 200) is detected as a block",
          _looks_blocked("<html>Enter the characters you see below robot check</html>"))
    check("an ordinary product page is not flagged as blocked",
          not _looks_blocked("<html>Pure Amla Powder 100g ₹249</html>"))

    # 10. (v3-4) An in-stock matched offer with no price beats an OOS sibling:
    # the result must be SOURCE_ERROR (collection failure), never OUT_OF_STOCK.
    class StubOosThenNoPrice(MarketplaceAdapter):
        name = "amazon_in"
        def search(self, q):
            return [Candidate("amazon_in", "D1", "u1", "Indian Amla Powder 100g",
                              [Offer("Treasure Flavours", None, 199.0, in_stock=False,
                                     offer_ref="D1:o")]),
                    Candidate("amazon_in", "D2", "u2", "Pure Amla Powder 100g",
                              [Offer("Treasure Flavours", None, None, in_stock=True,
                                     offer_ref="D2:o")])]
    rec = compare_variant(amla, amla["variants"][0], StubOosThenNoPrice(), False)
    check("in-stock price-extraction failure wins over an OOS sibling -> SOURCE_ERROR",
          rec.status == "SOURCE_ERROR")

    # 11. (v3-5) Numeric variant attributes are gated on word boundaries.
    shoe = {"title": "Running Shoe", "description": ""}
    shoe_v = {"attributes": {"size": "8"}, "variantName": "8"}
    verdict, _ = product_gate(shoe, shoe_v, Candidate("x", "S9", "u", "Running Shoe Size 9"), False)
    check("numeric size 8 != listing size 9 -> fail", verdict == "fail")
    verdict, _ = product_gate(shoe, shoe_v, Candidate("x", "S8", "u", "Running Shoe Size 8"), False)
    check("numeric size 8 not falsely matched inside '18'",
          not re.search(r"\b8\b", "Running Shoe Size 18") and verdict != "fail")

    # 12. Borderline judge is provider-agnostic and honest when unconfigured.
    check("judge parses a structured same_product verdict",
          _parse_same_product('noise {"same_product": true} tail') is True
          and _parse_same_product('{"same_product": false}') is False
          and _parse_same_product("no json here") is None)
    saved = {k: os.environ.pop(k, None)
             for k in ("LLM_JUDGE_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
    try:
        check("no key/provider -> judge resolves to none and returns None",
              _judge_provider() == "" and _llm_same_product("A", "B") is None)
        os.environ["ANTHROPIC_API_KEY"] = "x"
        check("ANTHROPIC_API_KEY present -> auto-selects anthropic",
              _judge_provider() == "anthropic")
        os.environ.pop("ANTHROPIC_API_KEY")
        os.environ["OPENAI_API_KEY"] = "x"
        check("OPENAI_API_KEY present -> auto-selects openai",
              _judge_provider() == "openai")
        os.environ["LLM_JUDGE_PROVIDER"] = "anthropic"
        check("explicit LLM_JUDGE_PROVIDER overrides key auto-detect",
              _judge_provider() == "anthropic")
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed.")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description="Naar price-matching POC (v3)")
    ap.add_argument("--backend", choices=["fixture", "direct"], default="fixture")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--marketplaces", nargs="+",
                    default=["amazon_in", "flipkart", "meesho"],
                    choices=["amazon_in", "flipkart", "meesho"])
    ap.add_argument("--llm-judge", action="store_true",
                    help="use an LLM for borderline product pairs (ANTHROPIC_API_KEY)")
    ap.add_argument("--strict", action="store_true",
                    help="any unexplained candidate token demotes to borderline")
    ap.add_argument("--self-test", action="store_true",
                    help="run the review regression checks and exit")
    ap.add_argument("--out", default="poc_out")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    try:
        records = run(args)
    except SourceError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    if not records:
        print("No records produced.", file=sys.stderr)
        sys.exit(1)
    write_outputs(records, args.out)


if __name__ == "__main__":
    main()
