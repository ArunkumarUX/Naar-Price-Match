#!/usr/bin/env python3
"""Accuracy evaluation for the Naar matcher (product gate + seller gate -> status).

Deterministic, offline, no LLM. Each case is a labeled (Naar product/variant,
marketplace candidate+offers) pair with a ground-truth status derived from the
brief's rules, plus a ground-truth 'same product?' label for gate-level metrics.

Reports: end-to-end status confusion + accuracy, and the cardinal safety metric —
MATCHED precision (of everything we call MATCHED, how many are truly same
product AND same seller). A false MATCHED is the brief's cardinal sin.
"""
import importlib.util
import os
import sys

_POC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naar_price_poc.py")
spec = importlib.util.spec_from_file_location("poc", _POC)
poc = importlib.util.module_from_spec(spec)
sys.modules["poc"] = poc
spec.loader.exec_module(poc)
Offer, Candidate = poc.Offer, poc.Candidate


def prod(title, desc, store, legal, variant_name, attrs, price=199.0):
    return ({"_id": "np", "title": title, "description": desc, "currency": "INR",
             "sellerId": "ns", "seller": {"storeName": store, "businessName": legal}},
            {"_id": "nv", "variantName": variant_name, "attributes": attrs,
             "sellingPrice": price})


class OneShot(poc.MarketplaceAdapter):
    def __init__(self, name, cands):
        self.name = name
        self._c = cands
    def search(self, q):
        return [c for c in self._c]


# (id, product, variant, candidate, expected_status, same_product_truth, note)
def C(title, offers, cid="L1"):
    return Candidate("amazon_in", cid, "http://x/" + cid, title, offers)


CASES = []
def add(cid, p, v, cand, exp, same, note):
    CASES.append((cid, p, v, cand, exp, same, note))


# --- TRUE MATCHES (exact product + same seller, purchasable) ---
p, v = prod("Amla Powder", "Pure Indian amla powder 100g.", "TREASURE FLAVOURS",
            "TREASURE FLAVOURS FOODS PRIVATE LIMITED", "100g", {"weight": "100g"})
add("m1", p, v, C("Pure Amla Powder (Indian Gooseberry) 100g",
                  [Offer("TREASURE FLAVOURS", None, 189.0)]), "MATCHED", True,
    "exact product, store name exact")
add("m2", p, v, C("Amla Powder 100g Indian Gooseberry",
                  [Offer(None, "TREASURE FLAVOURS FOODS PVT LTD", 205.0)]), "MATCHED", True,
    "PVT LTD vs PRIVATE LIMITED legal-name match")
add("m3", p, v, C("Indian Amla Powder 100 g",
                  [Offer("Flavours Treasure Foods", None, 199.0)]), "MATCHED", True,
    "word-reordered store name (token_set)")

# --- SAME PRODUCT, DIFFERENT SELLER -> must NOT be MATCHED ---
add("o1", p, v, C("Pure Amla Powder 100g",
                  [Offer("RetailNet India", "RETAILNET LOGISTICS LLP", 175.0)]),
    "SOLD_BY_OTHER", True, "product ok, clearly different seller")
add("o2", p, v, C("Amla Powder 100g",
                  [Offer("Reliance Retail", None, 180.0)]),
    "SOLD_BY_OTHER", True, "different seller (not our Treasure Flavours)")

# --- SAME PRODUCT, SELLER HIDDEN / NEAR-MISS -> AMBIGUOUS (never MATCHED) ---
add("a1", p, v, C("Pure Amla Powder 100g", [Offer(None, None, 190.0)]),
    "AMBIGUOUS_MATCH", True, "seller hidden -> ambiguous, not matched")
add("a2", p, v, C("Amla Powder 100g",
                  [Offer("Treasure Flavour", None, 195.0)]),
    "AMBIGUOUS_MATCH", True, "near-miss seller name (singular) -> proposal only")

# --- DERIVATIVE / WRONG PRODUCT -> must NOT match on product ---
add("p1", p, v, C("Amla Powder Hair Mask 100g",
                  [Offer("TREASURE FLAVOURS", None, 250.0)]),
    "AMBIGUOUS_MATCH", False, "derivative product, same seller -> not a product match")
add("p2", p, v, C("Bhringraj Powder 100g",
                  [Offer("TREASURE FLAVOURS", None, 210.0)]),
    "AMBIGUOUS_MATCH", False, "different herb, shares 'powder' — gate abstains, judge rejects")
add("p3", p, v, C("Amla Juice 1L",
                  [Offer("TREASURE FLAVOURS", None, 300.0)]),
    "AMBIGUOUS_MATCH", False, "different form (juice vs powder), shares 'amla' — gate abstains, judge rejects")

# --- QUANTITY / VARIANT MISMATCH -> product fail ---
add("q1", p, v, C("Pure Amla Powder 250g",
                  [Offer("TREASURE FLAVOURS", None, 300.0)]),
    "MATCHED", True, "100g vs 250g: same product, compared per-unit (₹300/2.5=₹120)")

ps, vs = prod("Kanchipuram Silk Cotton Saree", "Handloom saree 6.2m.",
              "Kaithari Kalanjiyam", "NITHYA VINOTH KUMAR", "Teal", {"colour": "Teal"}, price=1499.0)
add("v1", ps, vs, C("Kanchipuram Silk Cotton Saree Maroon",
                    [Offer("Kaithari Kalanjiyam", None, 1599.0)]),
    "PRODUCT_NOT_FOUND", False, "wrong colour variant Teal vs Maroon")
add("v2", ps, vs, C("Kanchipuram Silk Cotton Saree Teal with Blouse",
                    [Offer("Kaithari Kalanjiyam", None, 1499.0)]),
    "MATCHED", True, "correct Teal variant, same seller")

# numeric size
psz, vsz = prod("Running Shoe", "Mesh running shoe.", "FastFeet", "FASTFEET SPORTS LLP",
                "8", {"size": "8"}, price=1200.0)
add("s1", psz, vsz, C("Running Shoe Size 9", [Offer("FastFeet", None, 1150.0)]),
    "PRODUCT_NOT_FOUND", False, "numeric size 8 vs 9")
add("s2", psz, vsz, C("Running Shoe Size 8", [Offer("FastFeet", None, 1180.0)]),
    "MATCHED", True, "numeric size 8 correct, same seller")

# --- OUT OF STOCK: matched seller+product but unpurchasable ---
add("x1", p, v, C("Pure Amla Powder 100g",
                  [Offer("TREASURE FLAVOURS", None, 199.0, in_stock=False)]),
    "OUT_OF_STOCK", True, "matched but out of stock")

# --- SOURCE ERROR: matched seller, price unextractable ---
add("e1", p, v, C("Pure Amla Powder 100g",
                  [Offer("TREASURE FLAVOURS", None, None, in_stock=True)]),
    "SOURCE_ERROR", True, "matched seller, price extraction failed")

# --- BUY-BOX WRONG SELLER but our seller present on AOD -> MATCHED to our seller ---
add("m4", p, v, C("Pure Amla Powder 100g",
                  [Offer("RetailNet India", None, 179.0),
                   Offer("TREASURE FLAVOURS", None, 199.0)]),
    "MATCHED", True, "our seller not in buy box but on listing -> match our offer")

# --- multiple candidates: wrong one first, right one second ---
add("m5", p, v, None, "MATCHED", True, "second candidate is the true match")
CASES[-1] = ("m5", p, v,
             [C("Amla Powder Hair Mask 100g", [Offer("TREASURE FLAVOURS", None, 250.0)], "wrong"),
              C("Pure Amla Powder 100g", [Offer("TREASURE FLAVOURS", None, 199.0)], "right")],
             "MATCHED", True, "first cand derivative, second exact")


def run():
    rows = []
    for cid, p, v, cand, exp, same, note in CASES:
        cands = cand if isinstance(cand, list) else [cand]
        rec = poc.compare_variant(p, v, OneShot("amazon_in", cands), llm_judge=False)
        rows.append((cid, exp, rec.status, same, note, rec))
    return rows


def main():
    rows = run()
    n = len(rows)
    correct = sum(1 for _, exp, got, *_ in rows if exp == got)

    print(f"{'id':<5}{'expected':<18}{'predicted':<18}{'ok':<4}note")
    print("-" * 96)
    for cid, exp, got, same, note, rec in rows:
        ok = "✓" if exp == got else "✗"
        print(f"{cid:<5}{exp:<18}{got:<18}{ok:<4}{note}")

    # Cardinal safety metric: false MATCHED (predicted MATCHED but not truly same+seller-matched).
    false_matched = [r for r in rows if r[2] == "MATCHED" and r[1] != "MATCHED"]
    pred_matched = [r for r in rows if r[2] == "MATCHED"]
    true_matched = [r for r in rows if r[1] == "MATCHED"]
    tp_matched = [r for r in rows if r[1] == "MATCHED" and r[2] == "MATCHED"]

    # "Never a wrong price": any predicted MATCHED whose ground-truth same_product is False.
    wrong_product_priced = [r for r in rows if r[2] == "MATCHED" and r[3] is False]

    print("\n=== end-to-end status ===")
    print(f"status accuracy: {correct}/{n} = {correct/n:.0%}")
    prec = len(tp_matched) / len(pred_matched) if pred_matched else 1.0
    rec = len(tp_matched) / len(true_matched) if true_matched else 1.0
    print(f"MATCHED precision: {len(tp_matched)}/{len(pred_matched)} = {prec:.0%}"
          f"   (false MATCHED: {len(false_matched)})")
    print(f"MATCHED recall:    {len(tp_matched)}/{len(true_matched)} = {rec:.0%}")

    print("\n=== CARDINAL SAFETY (brief's #1 rule) ===")
    print(f"MATCHED rows on a NOT-same product: {len(wrong_product_priced)}  "
          f"(must be 0 — a priced row on a wrong product)")
    print(f"MATCHED rows on a different SELLER: "
          f"{len([r for r in rows if r[2]=='MATCHED' and r[1] in ('SOLD_BY_OTHER','AMBIGUOUS_MATCH')])}  (must be 0)")

    # Product-gate discrimination (same vs different), abstentions counted separately.
    print("\n=== confusion (rows where predicted != expected) ===")
    misses = [(cid, exp, got, note) for cid, exp, got, _, note, _ in rows if exp != got]
    if not misses:
        print("  none")
    for cid, exp, got, note in misses:
        print(f"  {cid}: expected {exp}, got {got}  ({note})")

    return 0 if not false_matched and not wrong_product_priced else 1


if __name__ == "__main__":
    sys.exit(main())
