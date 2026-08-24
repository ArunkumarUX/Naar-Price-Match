#!/usr/bin/env python3
"""Live borderline-judge smoke test against a REAL vendor. Provider + keys come
from the environment (set by the caller). Prints only verdicts, never keys."""
import importlib.util
import os
import sys

_POC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naar_price_poc.py")
spec = importlib.util.spec_from_file_location("poc", _POC)
poc = importlib.util.module_from_spec(spec)
sys.modules["poc"] = poc
spec.loader.exec_module(poc)

prov = poc._judge_provider()
model = os.environ.get("OPENAI_MODEL") if prov == "openai" else os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
base = os.environ.get("OPENAI_BASE_URL", "api.anthropic.com") if prov == "openai" else "api.anthropic.com"
print(f"provider={prov} model={model} endpoint={base}")

pairs = [
    ("SAME ", "Amla Powder 100g (Indian Gooseberry)", "Pure Amla Powder 100g", True),
    ("DIFF ", "Amla Powder 100g", "Amla Powder Hair Mask 100g", False),
]
ran = 0
for label, a, b, expected in pairs:
    v = poc._llm_same_product(a, b)
    if v is None:
        print(f"  {label} verdict=None  -> judge UNAVAILABLE (key/endpoint/model problem)")
    else:
        ran += 1
        tag = "matches expectation" if v is expected else "vendor disagrees (model judgment, not a wiring bug)"
        print(f"  {label} verdict={v!s:<5} expected={expected!s:<5} -> {tag}")
# Success = the adapter reached a real vendor and got a structured bool at least once.
sys.exit(0 if ran > 0 else 3)
