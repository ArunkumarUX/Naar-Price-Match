# Naar marketplace price-matching — POC

For each active Naar product, find the **same seller** selling the **same
product/variant** on a marketplace and record the comparable INR price — only
when the seller's store is **human-verified** and the product genuinely matches.
Every row carries an honest status; a price is written only on a `MATCHED` row.

Two decisions shaped this design, both proven the hard way:
- **Store names differ across platforms and can't be reliably auto-matched** →
  so the store is **verified once by a human**, then products are looked up only
  inside that verified store (store-first).
- **Scraping HTML with a headless browser fails at scale** (~55% blocked) → so
  fetching goes through a **structured data API** that returns reliable JSON.

---

## Quick start

```bash
pip install requests                      # + beautifulsoup4 only if you extend adapters
```

**1 · Sanity (offline, no keys):**
```bash
python poc/naar_price_poc.py --self-test        # regression checks
python poc/eval_accuracy.py                      # matcher precision (0 false matches)
python poc/naar_price_poc.py --backend fixture   # offline demo (sellers pre-confirmed)
python poc/prove_llm.py                          # provider-agnostic judge proof (mock)
```

**2 · Verify stores** (the human step) — needs `SCRAPERAPI_KEY` in `poc/.env`:
```bash
python poc/verify_app.py        # open http://127.0.0.1:8765  (--fixture for offline sellers)
```
For each seller it **auto-proposes** candidate stores (searches by the store/brand
name, lists the distinct sellers behind the results ranked by similarity). You
**Confirm** one, **paste** the correct store URL, or mark **Not on** that
marketplace. Choices persist to `poc/seller_identity.json` (the store registry).

**3 · Store-first run** — only verified stores are looked up:
```bash
python poc/naar_price_poc.py --backend direct --limit 15 --marketplaces amazon_in --llm-judge
```

### CLI flags
| Flag | Default | Meaning |
|------|---------|---------|
| `--backend fixture\|direct` | `fixture` | offline demo vs live Naar API + marketplace |
| `--limit` / `--skip` | `10` / `0` | Naar product pagination |
| `--marketplaces` | `amazon_in` | `amazon_in` (structured) + FK/Meesho stubs |
| `--llm-judge` | off | adjudicate *borderline* product pairs (never sets price/seller) |
| `--strict` | off | any unexplained candidate token demotes to borderline |
| `--out` | `poc_out` | output dir |

---

## How it works

```
verify store (human, once)   →  structured-API search (JSON: name, price, sold_by)
   →  keep the confirmed store's offers   →  the store filter replaces fuzzy seller guessing
   →  product gate (GTIN → per-unit → attributes → coverage → judge)
   →  per-unit price compare               →  MATCH = same product, from the verified store
```

**1 · Verify the store** (`verify_app.py`, `propose_stores`, `confirm_store`).
A human confirms each Naar seller's store per marketplace → `seller_identity.json`,
with a per-marketplace status (`confirmed` / `rejected` / `pending`).

**2 · Fetch** (`AmazonInAdapter`, `_scraperapi_structured`). Amazon via ScraperAPI's
structured endpoints — parsed JSON (`pricing`, `list_price`/MRP, `sold_by`,
availability), no HTML parsing. Flipkart/Meesho have no structured endpoint yet,
so they're **honest stubs** that raise until a provider is wired.

**3 · Product gate** (`product_gate`) → `pass` / `fail` / `borderline`:
- **GTIN/barcode** — both expose one and match → same product; mismatch → fail.
- **Per-unit** — a single-unit-vs-multipack (100g vs 250g) is the same product in a
  different size: record the ratio and compare **per unit** (₹259 pack-of-5 → ₹51.8).
- **Attributes** — colour/size must appear as whole words (`Teal` ≠ inside `Steal`).
- **Coverage vs unexplained ratio** — a derivative (`Amla Powder Hair Mask`) is
  dominated by unexplained tokens → borderline, never an auto-pass.
- **LLM judge** (optional) adjudicates only the borderlines.

**4 · Store filter + decision** (`compare_variant`, `_offer_matches_store`). The
seller is already human-verified, so a `MATCHED` = the **confirmed store** is
selling this product (matched by seller-URL token, else by `sold_by` name). Only
the confirmed store's offers can match; any other seller of the same product is
recorded as `other_sellers` **competitive intel** — never our match.

### Statuses
| Status | Meaning |
|--------|---------|
| `MATCHED` | confirmed store sells the same product, in stock — price + Δ recorded |
| `PRODUCT_NOT_FOUND` | not the same product, or the confirmed store isn't selling it (competitors noted) |
| `OUT_OF_STOCK` | confirmed store + product, not purchasable |
| `SOURCE_ERROR` | fetch failed, or matched but price unextractable |
| *(needs review)* | store not verified yet — skipped, no fetch (stderr) |

**Price integrity:** a price is written **only** on `MATCHED`, from the verified
store's structured offer. `Record.__post_init__` nulls the price fields on every
non-MATCHED row; competitor prices live in `other_sellers`.

---

## Environment (`poc/.env`, gitignored, loaded by `_load_dotenv`)
| Var | Purpose |
|-----|---------|
| `SCRAPERAPI_KEY` | ScraperAPI structured endpoints (Amazon fetch + store proposals) |
| `LLM_JUDGE_PROVIDER` | `anthropic` \| `openai` (default: auto by which key is set) |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Anthropic judge |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | any OpenAI-compatible judge |
| `NAAR_KYC_FILE` | store-registry path (default `poc/seller_identity.json`) |
| `MATCH_COVERAGE_FAIL` / `MATCH_COVERAGE_PASS` / `MATCH_MAX_UNEXPLAINED_RATIO` | product-gate tuning |

---

## Files
| File | What it is |
|------|-----------|
| `naar_price_poc.py` | The POC — Naar pull, structured Amazon adapter, product gate, store-first match, per-unit price, optional judge, six honest statuses. Ships `--self-test`. |
| `verify_app.py` | Store-verification web tool: auto-proposes stores, Confirm/Reject/Paste-URL, writes the registry. |
| `eval_accuracy.py` | Labeled harness — the cardinal metric: **MATCHED precision / zero false matches**. |
| `prove_llm.py` | Judge proof against a local mock OpenAI-compatible server (no secrets, no network). |
| `live_judge.py` | Live judge smoke test; provider/keys from env. |
| `make_sheet.py` | Turns a run into a shareable CSV (Excel/Sheets). |
| `seller_identity.example.json` | Store-registry template (copy to `seller_identity.json`, gitignored). |

## Scope & caveats
- Live fetch is **Amazon-only** today (the one marketplace with a structured
  endpoint); Flipkart/Meesho need a structured provider wired to their stubs.
- Structured API is **paid** (ScraperAPI credits) — the reliable path at scale.
- Coverage is bounded by **store verification + product/seller presence**: the tool
  reports the truth (`PRODUCT_NOT_FOUND`, competitor intel) rather than faking a match.
