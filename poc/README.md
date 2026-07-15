# Naar marketplace price-matching — POC

Proof-of-concept for the price-matching brief: for each active Naar product,
find the *same seller* selling the *same product/variant* on Amazon India,
Flipkart, and Meesho, and record the comparable INR price — only when both the
product gate and the seller gate pass. Every row carries an honest status; a
marketplace price is written **only** on `MATCHED` rows, from structured offer
data, never a guess.

## Files

| File | What it is |
|------|-----------|
| `naar_price_poc.py` | The POC. Naar API pull, per-marketplace adapters, product + seller gates, six honest statuses (`MATCHED`, `SOLD_BY_OTHER`, `PRODUCT_NOT_FOUND`, `AMBIGUOUS_MATCH`, `OUT_OF_STOCK`, `SOURCE_ERROR`). Ships its own `--self-test`. |
| `eval_accuracy.py` | Labeled accuracy harness over the matcher (offline, deterministic). Reports status accuracy + the cardinal metric: **MATCHED precision / zero false matches**. |
| `prove_llm.py` | End-to-end proof of the provider-agnostic borderline judge against a local mock OpenAI-compatible server (no secrets, no network). |
| `live_judge.py` | Live smoke test of the judge against a real vendor. Provider/keys come from env; prints only verdicts. |

## Run

```bash
python poc/naar_price_poc.py --self-test              # unit regressions (offline)
python poc/naar_price_poc.py --backend fixture        # offline demo, all six statuses
python poc/eval_accuracy.py                           # matcher accuracy report
python poc/prove_llm.py                               # mock-server judge proof
python poc/naar_price_poc.py --backend direct --limit 10   # live run (needs SCRAPERAPI_KEY / access)
```

Direct-fetch marketplaces need network access; Amazon/Flipkart/Meesho commonly
soft-block, and Meesho needs `SCRAPERAPI_KEY`. Blocks surface as `SOURCE_ERROR`,
never a silent `PRODUCT_NOT_FOUND`.

## Borderline LLM judge (optional)

Rules only on product-gate *borderlines* — never sets a price or seller.
`LLM_JUDGE_PROVIDER=anthropic|openai` (default: auto by key). `openai` also
drives any OpenAI-compatible vendor via `OPENAI_BASE_URL`
(OpenAI / Qwen / DeepSeek / Groq / OpenRouter / local Ollama). No key → judge is
skipped and the gate stays honestly borderline.

Dependencies: `requests` and `beautifulsoup4` for live/direct runs; `--self-test`,
`fixture`, `eval_accuracy.py`, and `prove_llm.py` run on the stdlib alone.
