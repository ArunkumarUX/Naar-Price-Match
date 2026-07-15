#!/usr/bin/env python3
"""Proof harness: drive the POC's provider-agnostic borderline judge through a
LOCAL mock OpenAI-compatible /chat/completions server. No secrets, no network,
deterministic. Proves: request shape, verdict parse (true/false), honest None on
bad/500 responses, and that the LLM verdict actually flips real pipeline output
(product_gate borderline -> pass/fail, and compare_variant -> MATCHED vs
PRODUCT_NOT_FOUND)."""
import http.server
import importlib.util
import json
import os
import sys
import threading

POC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naar_price_poc.py")
spec = importlib.util.spec_from_file_location("poc", POC)
poc = importlib.util.module_from_spec(spec)
sys.modules["poc"] = poc          # dataclass forward-ref introspection needs this
spec.loader.exec_module(poc)

# Mutable server behaviour, set per test.
STATE = {"content": '{"same_product": true}', "code": 200}
CAPTURED = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n)
        CAPTURED.clear()
        CAPTURED["path"] = self.path
        CAPTURED["auth"] = self.headers.get("Authorization")
        CAPTURED["body"] = json.loads(body or b"{}")
        if STATE["code"] != 200:
            self.send_response(STATE["code"])
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        payload = {"choices": [{"message": {"role": "assistant",
                                            "content": STATE["content"]}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)


httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

os.environ["LLM_JUDGE_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
os.environ["OPENAI_MODEL"] = "mock-model-x"

fails = []


def check(label, cond):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        fails.append(label)


print(f"mock OpenAI-compatible server on 127.0.0.1:{port}\n")

# 1. Verdict true -> True, and the request we SENT is correctly shaped.
STATE.update(content='{"same_product": true}', code=200)
r = poc._llm_same_product("Amla Powder 100g", "Pure Amla Powder 100g")
check("openai path: same_product true -> True", r is True)
check("  -> POSTed to /v1/chat/completions", CAPTURED["path"].endswith("/chat/completions"))
check("  -> Authorization: Bearer <key>", CAPTURED["auth"] == "Bearer test-key-123")
check("  -> model forwarded from OPENAI_MODEL", CAPTURED["body"].get("model") == "mock-model-x")
check("  -> user message carries both products",
      "Amla Powder 100g" in json.dumps(CAPTURED["body"]["messages"]))
check("  -> deterministic temperature=0", CAPTURED["body"].get("temperature") == 0)

# 2. Verdict false -> False.
STATE.update(content='{"same_product": false}')
check("openai path: same_product false -> False",
      poc._llm_same_product("A", "B") is False)

# 3. Model returns prose around JSON -> still parsed.
STATE.update(content='Sure! {"same_product": true} hope that helps')
check("openai path: JSON embedded in prose still parses -> True",
      poc._llm_same_product("A", "B") is True)

# 4. Honest None: unparseable body.
STATE.update(content="I think they are the same, yes.")
check("openai path: no JSON -> None (stays borderline)",
      poc._llm_same_product("A", "B") is None)

# 5. Honest None: HTTP 500.
STATE.update(content='{"same_product": true}', code=500)
check("openai path: HTTP 500 -> None (never fabricates)",
      poc._llm_same_product("A", "B") is None)
STATE.update(code=200)

# 6. The judge actually FLIPS product_gate on a real borderline pair.
amla = poc.FIXTURE_NAAR[0]
borderline = poc.Candidate("x", "Y", "u", "Amla Powder Hair Mask 100g")
v_nojudge, _ = poc.product_gate(amla, amla["variants"][0], borderline, llm_judge=False)
check("borderline pair is 'borderline' without a judge", v_nojudge == "borderline")
STATE.update(content='{"same_product": true}')
v_true, _ = poc.product_gate(amla, amla["variants"][0], borderline, llm_judge=True)
check("judge=true promotes borderline -> pass", v_true == "pass")
STATE.update(content='{"same_product": false}')
v_false, _ = poc.product_gate(amla, amla["variants"][0], borderline, llm_judge=True)
check("judge=false demotes borderline -> fail", v_false == "fail")

# 7. End-to-end: the LLM verdict changes the final Record status.
class BorderlineStub(poc.MarketplaceAdapter):
    name = "amazon_in"
    def search(self, q):
        return [poc.Candidate(
            "amazon_in", "C1", "u1", "Amla Powder Hair Mask 100g",
            [poc.Offer("Treasure Flavours", None, 199.0, offer_ref="C1:o")])]

STATE.update(content='{"same_product": false}')
rec_f = poc.compare_variant(amla, amla["variants"][0], BorderlineStub(), llm_judge=True)
check("compare_variant: judge=false -> PRODUCT_NOT_FOUND, no price",
      rec_f.status == "PRODUCT_NOT_FOUND" and rec_f.marketplace_selling_price is None)
STATE.update(content='{"same_product": true}')
rec_t = poc.compare_variant(amla, amla["variants"][0], BorderlineStub(), llm_judge=True)
check("compare_variant: judge=true + matched seller -> MATCHED @ ₹199",
      rec_t.status == "MATCHED" and rec_t.marketplace_selling_price == 199.0)

httpd.shutdown()
print(f"\n{len(fails)} failure(s)" if fails else "\nAll proofs passed.")
raise SystemExit(1 if fails else 0)
