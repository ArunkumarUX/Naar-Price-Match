#!/usr/bin/env python3
"""Manual store-verification tool (store-first workflow).

A tiny local web app (stdlib http.server, no extra deps) that curates the store
registry `poc/seller_identity.json`: for each Naar seller it auto-proposes
candidate marketplace stores (search by store/brand name), and the reviewer
CONFIRMS one, pastes the correct store URL, or marks the seller "not on" the
marketplace. Confirmed stores then drive `naar_price_poc.py --store-first`.

Run:  python poc/verify_app.py           # live Naar sellers (needs network)
      python poc/verify_app.py --fixture # offline demo sellers
Then open http://127.0.0.1:8765
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naar_price_poc as poc  # noqa: E402

poc._load_dotenv()
MARKETPLACES = ("amazon_in", "flipkart", "meesho")
USE_FIXTURE = "--fixture" in sys.argv
_sellers_cache: list = []
_lock = threading.Lock()


def _adapter(marketplace: str):
    return {"amazon_in": poc.AmazonInAdapter, "flipkart": poc.FlipkartAdapter,
            "meesho": poc.MeeshoAdapter}[marketplace]()


def load_naar_sellers(limit: int = 200) -> list:
    """Distinct Naar sellers (id, store name, business name) from the catalogue."""
    global _sellers_cache
    if _sellers_cache:
        return _sellers_cache
    products = poc.FIXTURE_NAAR if USE_FIXTURE else poc.fetch_naar_products(limit, 0)
    by_id: dict = {}
    for p in products:
        sid = str(p.get("sellerId") or "")
        if not sid or sid in by_id:
            continue
        s = p.get("seller") or {}
        by_id[sid] = {"seller_id": sid,
                      "store_name": s.get("storeName") or "",
                      "business_name": s.get("businessName") or ""}
    _sellers_cache = sorted(by_id.values(), key=lambda x: x["store_name"].lower())
    return _sellers_cache


def sellers_with_status() -> list:
    out = []
    for s in load_naar_sellers():
        out.append({**s, "status": {m: poc.store_status(s["seller_id"], m) for m in MARKETPLACES}})
    return out


PAGE = """<!doctype html><meta charset=utf-8><title>Naar store verification</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#111;background:#faf9f7}
 h1{font-size:20px} table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #e5e2dc;padding:8px 10px;text-align:left;vertical-align:top}
 .st{font-size:12px;padding:2px 8px;border-radius:999px} .confirmed{background:#d6f5d6} .rejected{background:#f5d6d6} .pending{background:#f0ede7;color:#666}
 button{font:13px system-ui;padding:5px 10px;border:1px solid #cbb;border-radius:6px;background:#fff;cursor:pointer;margin:2px}
 button.primary{background:#00CCDD;border-color:#00b3c2} .cands{background:#fff;border:1px solid #e5e2dc;border-radius:8px;padding:10px;margin-top:6px}
 .cand{display:flex;gap:8px;align-items:center;justify-content:space-between;border-bottom:1px solid #eee;padding:6px 0}
 input[type=text]{padding:5px;border:1px solid #cbb;border-radius:6px;width:340px} .muted{color:#888;font-size:12px} a{color:#0077aa}
</style>
<h1>Naar store verification <span class=muted>— confirm each seller's marketplace store before price lookup</span></h1>
<p class=muted>Confirm the seller's real store on a marketplace (or paste its URL), or mark "not on". Confirmed stores drive <code>--store-first</code>.</p>
<table id=t><thead><tr><th>Seller (Naar)</th><th>Amazon</th><th>Flipkart</th><th>Meesho</th></tr></thead><tbody></tbody></table>
<script>
const MK=["amazon_in","flipkart","meesho"];
async function j(u,o){const r=await fetch(u,o);return r.json()}
function stChip(s){return `<span class="st ${s}">${s}</span>`}
async function load(){
 const rows=await j('/api/sellers');const tb=document.querySelector('#t tbody');tb.innerHTML='';
 for(const s of rows){
  const tr=document.createElement('tr');
  let cells=`<td><b>${s.store_name||'(no store name)'}</b><div class=muted>${s.business_name||''}<br>${s.seller_id}</div></td>`;
  for(const m of MK){cells+=`<td id="c_${s.seller_id}_${m}">${stChip(s.status[m])}<br>
     <button onclick="verify('${s.seller_id}','${m}')">Verify</button>
     <button onclick="reject('${s.seller_id}','${m}')">Not on</button></td>`}
  tr.innerHTML=cells;tb.appendChild(tr);
 }
}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function verify(sid,m){
 const cell=document.getElementById(`c_${sid}_${m}`);
 let box=cell.querySelector('.cands');
 if(box)box.remove();                       // fix: replace, never stack multiple result boxes
 box=document.createElement('div');box.className='cands';box.textContent='searching…';
 cell.appendChild(box);
 const cs=await j(`/api/propose?seller=${encodeURIComponent(sid)}&marketplace=${m}`);
 box.textContent='';
 if(cs.error){box.innerHTML=`<div class=muted>could not search: ${esc(cs.error)}</div>`}
 else if(!cs.length){box.innerHTML='<div class=muted>no candidate sellers found</div>'}
 else for(const c of cs){
   const row=document.createElement('div');row.className='cand';
   const info=document.createElement('div');
   info.innerHTML=`${esc(c.seller_display)} <span class=muted>(sim ${esc(String(c.similarity))})<br>e.g. ${esc((c.sample_title||'').slice(0,54))} ${c.sample_listing?`· <a href="${esc(c.sample_listing)}" target=_blank>listing</a>`:''}</span>`;
   const btn=document.createElement('button');btn.className='primary';btn.textContent='Confirm';
   btn.onclick=()=>confirmStore(sid,m,c.store_url||"",c.seller_display);   // closure: real values, no HTML-attr injection
   row.appendChild(info);row.appendChild(btn);box.appendChild(row);
 }
 const urow=document.createElement('div');urow.className='cand';
 const inp=document.createElement('input');inp.type='text';inp.id=`u_${sid}_${m}`;inp.placeholder='…or paste the correct store URL';
 const ubtn=document.createElement('button');ubtn.textContent='Confirm URL';ubtn.onclick=()=>confirmUrl(sid,m);
 urow.appendChild(inp);urow.appendChild(ubtn);box.appendChild(urow);
}
async function confirmStore(sid,m,url,disp){
 await j('/api/confirm',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m,store_url:url,seller_display:disp})});load();}
async function confirmUrl(sid,m){
 const url=document.getElementById(`u_${sid}_${m}`).value.trim();if(!url)return;
 // Also carry the Naar store name: Amazon's structured API matches offers by the
 // Sold-by NAME (not a URL), so a URL-only confirm would never match live.
 const name=document.getElementById(`c_${sid}_${m}`).closest('tr').querySelector('b').textContent.trim();
 await j('/api/confirm',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m,store_url:url,seller_display:name})});load();}
async function reject(sid,m){await j('/api/reject',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m})});load();}
load();
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        try:                                     # a corrupt registry -> 500 JSON, not a crashed handler
            if u.path == "/api/sellers":
                return self._send(200, json.dumps(sellers_with_status()))
            if u.path == "/api/propose":
                q = parse_qs(u.query)
                sid = (q.get("seller") or [""])[0]
                m = (q.get("marketplace") or [""])[0]
                seller = next((s for s in load_naar_sellers() if s["seller_id"] == sid), None)
                name = (seller or {}).get("store_name") or (seller or {}).get("business_name") or ""
                if not name:
                    return self._send(200, json.dumps({"error": "seller has no store/business name"}))
                with _lock:
                    cands = poc.propose_stores(name, m, _adapter(m))
                if cands and cands[0].get("error"):
                    return self._send(200, json.dumps({"error": cands[0]["error"]}))
                return self._send(200, json.dumps(cands))
        except poc.SourceError as e:
            return self._send(500, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("content-length", 0) or 0)   # bad header -> 400, not a crash
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, json.dumps({"error": "bad request body"}))
        if not isinstance(body, dict):                            # JSON null/array/scalar -> 400
            return self._send(400, json.dumps({"error": "body must be a JSON object"}))
        try:
            if u.path == "/api/confirm":
                poc.confirm_store(body["seller_id"], body["marketplace"],
                                  body.get("store_url", ""), body.get("seller_display", ""))
                return self._send(200, json.dumps({"ok": True}))
            if u.path == "/api/reject":
                poc.reject_store(body["seller_id"], body["marketplace"])
                return self._send(200, json.dumps({"ok": True}))
        except poc.SourceError as e:                              # e.g. corrupt registry
            return self._send(500, json.dumps({"error": str(e)}))
        except (KeyError, ValueError, TypeError) as e:            # missing/typed-wrong fields
            return self._send(400, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))


def main():
    port = int(os.environ.get("VERIFY_PORT", "8765"))
    src = "fixture" if USE_FIXTURE else "live Naar API"
    print(f"Store verification: {len(load_naar_sellers())} sellers ({src})")
    print(f"Open http://127.0.0.1:{port}  (writes {poc._registry_path()})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
