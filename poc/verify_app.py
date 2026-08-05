#!/usr/bin/env python3
"""Manual store-verification tool (store-first workflow).

A tiny local web app (stdlib http.server, no extra deps) that curates the store
registry `poc/seller_identity.json`: for each Naar seller it auto-proposes
candidate marketplace stores (search by store/brand name), and the reviewer
CONFIRMS one, pastes the correct store URL, or marks the seller "not on" the
marketplace. Confirmed stores then drive `naar_price_poc.py --store-first`.

Run:  python poc/verify_app.py           # live Naar sellers, whole catalogue (paged)
      python poc/verify_app.py --fixture # offline demo sellers
Then open http://127.0.0.1:8765
Env:  VERIFY_LIMIT=N   cap on catalogue products paged (default 5000)
      VERIFY_PORT=N    listen port (default 8765)
"""
import concurrent.futures
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
_sellers_ready = False          # set once the (paged) seller list has loaded
_sellers_error = ""             # non-empty if the live catalogue fetch failed
_lock = threading.Lock()

import results_store
_products_cache: list = []
_job = {"status": "idle", "done": 0, "total": 0, "run_id": None, "started": "", "error": ""}
_job_lock = threading.Lock()


def _int(v, default):
    """Safe int conversion with fallback for non-numeric values."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _adapter(marketplace: str):
    return {"amazon_in": poc.AmazonInAdapter, "flipkart": poc.FlipkartAdapter,
            "meesho": poc.MeeshoAdapter}[marketplace]()


def _fetch_page(skip: int, page_size: int, tries: int = 3):
    """One catalogue page, retried on transient failures. Returns None if it still
    fails after `tries` — so one flaky page can't blank the whole seller list."""
    for attempt in range(tries):
        try:
            return poc.fetch_naar_products(page_size, skip)
        except poc.SourceError as e:
            if attempt == tries - 1:
                print(f"[verify_app] page skip={skip} failed after {tries} tries: {e}", file=sys.stderr)
                return None
    return None


def _all_naar_products() -> list:
    """Page through the whole Naar catalogue. The API caps at ~100 products/page,
    so a single fetch only sees page 1 (~14 sellers). The pages are independent,
    so fetch them a batch at a time CONCURRENTLY (serial paging is ~2 min; batched
    is ~10s), retrying transient blips. The catalogue ends only at a genuinely
    EMPTY page — a short (partial) page or a single failed page must NOT truncate
    the rest, or later sellers (e.g. those past a mid-catalogue hiccup) silently
    vanish. Bounded by VERIFY_LIMIT so a mis-paginating API can't run away."""
    cap = int(os.environ.get("VERIFY_LIMIT", "5000"))
    page_size, batch = 100, 8
    out: list = []
    base = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=batch) as ex:
        while len(out) < cap:
            skips = [base + i * page_size for i in range(batch)]
            pages = list(ex.map(lambda sk: _fetch_page(sk, page_size), skips))
            stop = False
            got_any = False
            for pg in pages:                 # in skip order
                if pg is None:               # failed after retries — skip it, keep the tail
                    continue
                got_any = True
                if len(pg) == 0:             # genuine end of catalogue
                    stop = True
                    break
                out.extend(pg)               # keep short-but-nonempty pages too, and continue
            if stop or not got_any:          # empty page = end; a wholly-failed batch = give up
                break
            base += batch * page_size
    return out[:cap]


def load_naar_sellers() -> list:
    """Distinct Naar sellers (id, store name, business name) across the FULL catalogue."""
    global _sellers_cache
    if _sellers_cache:
        return _sellers_cache
    products = poc.FIXTURE_NAAR if USE_FIXTURE else _all_naar_products()
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


def _catalogue() -> list:
    """Full product list for a run (cached). Fixture list offline; live catalogue otherwise."""
    global _products_cache
    if _products_cache:
        return _products_cache
    _products_cache = list(poc.FIXTURE_NAAR) if USE_FIXTURE else _all_naar_products()
    return _products_cache


def _adapters() -> dict:
    # Offline demo (--fixture) must use fixture adapters, else a run hits the live
    # network. scan_confirmed binds them per product (they're keyed by product id).
    if USE_FIXTURE:
        return {m: poc.FixtureAdapter(m) for m in MARKETPLACES}
    return {m: _adapter(m) for m in MARKETPLACES}


def _run_scan_job(plan) -> None:
    """Background worker: run the plan, persist to SQLite, update _job."""
    try:
        def progress(done, total):
            with _job_lock:
                _job["done"], _job["total"] = done, total
        # Enable the store-scoped LLM borderline-judge automatically when a provider
        # key is configured (Anthropic/OpenAI-compatible). It only adjudicates
        # borderline candidates sold by the confirmed store; no key -> deterministic.
        use_llm = bool(poc._judge_provider())
        records = poc.scan_confirmed(plan, _adapters(), progress_cb=progress, llm_judge=use_llm)
        rows = [__import__("dataclasses").asdict(r) for r in records]
        n_sellers = len({r.get("naar_seller_id") for r in rows})
        n_products = len({r.get("naar_product_id") for r in rows})
        rid = results_store.save_run(
            {"started_at": _job["started"], "finished_at": poc._now_iso(), "status": "done",
             "total": len(plan), "done": len(plan), "seller_count": n_sellers,
             "product_count": n_products, "api_calls_est": len(plan) * 6, "error": ""},
            rows)
        with _job_lock:
            _job.update(status="done", run_id=rid, done=len(plan), total=len(plan))
    except Exception as e:                    # never leave the job stuck on "running"
        with _job_lock:
            _job.update(status="error", error=f"{type(e).__name__}: {e}")


# High-similarity auto-confirm sweep (separate job from the price-match run).
_sweep_job = {"status": "idle", "done": 0, "total": 0, "confirmed": 0, "started": "", "error": ""}
_sweep_lock = threading.Lock()


def _run_sweep_job(plan) -> None:
    """Background worker: discover + auto-confirm high-similarity pending stores."""
    try:
        def progress(done, total):
            with _sweep_lock:
                _sweep_job["done"], _sweep_job["total"] = done, total
        results = poc.auto_confirm_sweep(plan, _adapters(), progress_cb=progress)
        n_confirmed = sum(1 for r in results if r.get("action") == "confirmed")
        with _sweep_lock:
            _sweep_job.update(status="done", confirmed=n_confirmed,
                              done=len(plan), total=len(plan))
    except Exception as e:
        with _sweep_lock:
            _sweep_job.update(status="error", error=f"{type(e).__name__}: {e}")


def warm_sellers() -> None:
    """Load the seller list once, in the background, so the server can serve the
    page immediately while the (paged) live catalogue is still downloading."""
    global _sellers_ready, _sellers_error
    try:
        load_naar_sellers()
    except Exception as e:                       # surface, don't hang the UI
        _sellers_error = f"{type(e).__name__}: {e}"
    finally:
        _sellers_ready = True


def sellers_with_status():
    """List for the UI, or a {loading|error} marker so the page can show progress
    instead of a blank table while the catalogue pages in."""
    if not _sellers_ready:
        return {"loading": True}
    if _sellers_error:
        return {"error": _sellers_error}
    return [{**s, "status": {m: poc.store_status(s["seller_id"], m) for m in MARKETPLACES}}
            for s in _sellers_cache]


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
<h1>Naar store verification <span id=cnt class=muted>— confirm each seller's marketplace store before price lookup</span></h1>
<div id=tabs style="margin:8px 0">
  <button id=tab_annotate class=primary>Annotate</button>
  <button id=tab_results>Results</button>
</div>
<div id=view_annotate>
<p class=muted>Confirm the seller's real store on a marketplace (or paste its URL), or mark "not on". Confirmed stores drive <code>--store-first</code>.</p>
<div id=sweep_panel style="margin:8px 0"></div>
<div id=bar style="display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap">
 <input type=text id=q placeholder="search seller / business / id" style="width:280px">
 <label class=muted>per page <select id=ps><option>25</option><option>50</option><option>100</option><option value=99999>all</option></select></label>
 <span style="flex:1"></span>
 <button id=prev>‹ Prev</button>
 <span id=pg class=muted>0</span>
 <button id=next>Next ›</button>
</div>
<table id=t><thead><tr><th>Seller (Naar)</th><th>Amazon</th><th>Flipkart</th><th>Meesho</th></tr></thead><tbody></tbody></table>
</div>
<div id=view_results style="display:none">
  <div id=run_panel style="margin:10px 0"></div>
  <div id=res_bar style="display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap">
    <input type=text id=rq placeholder="filter by seller" style="width:240px">
    <select id=rstatus>
      <option value="">all statuses</option>
      <option>MATCHED</option><option>PRODUCT_NOT_FOUND</option>
      <option>OUT_OF_STOCK</option><option>SOURCE_ERROR</option>
    </select>
    <a id=dlcsv href="/api/results/export.csv"><button>Download CSV</button></a>
    <span style="flex:1"></span>
    <button id=rprev>‹ Prev</button><span id=rpg class=muted>0</span><button id=rnext>Next ›</button>
  </div>
  <table id=rt><thead><tr>
    <th>Seller</th><th>Product</th><th>Market</th><th>Naar ₹</th><th>Mkt ₹</th>
    <th>Δ</th><th>Status</th><th>Sold by</th><th>Also sold by</th>
  </tr></thead><tbody></tbody></table>
</div>
<script>
const MK=["amazon_in","flipkart","meesho"];
let ALL=[],PAGE=0,PSIZE=25,FILT='';
async function j(u,o){const r=await fetch(u,o);return r.json()}
function stChip(s){return `<span class="st ${s}">${s}</span>`}
async function load(){
 const data=await j('/api/sellers');const tb=document.querySelector('#t tbody');const cnt=document.getElementById('cnt');
 if(data&&data.loading){cnt.textContent='— loading Naar sellers (paging catalogue)…';tb.innerHTML='<tr><td colspan=4 class=muted>loading…</td></tr>';setTimeout(load,2000);return;}
 if(data&&data.error){cnt.textContent='';tb.innerHTML=`<tr><td colspan=4 class=muted>could not load sellers: ${esc(data.error)}</td></tr>`;return;}
 ALL=data;render();
}
function render(){
 const tb=document.querySelector('#t tbody');const cnt=document.getElementById('cnt');
 const f=FILT.trim().toLowerCase();
 const rows=f?ALL.filter(s=>((s.store_name||'')+' '+(s.business_name||'')+' '+(s.seller_id||'')).toLowerCase().includes(f)):ALL;
 const pages=Math.max(1,Math.ceil(rows.length/PSIZE));
 if(PAGE>=pages)PAGE=pages-1; if(PAGE<0)PAGE=0;
 const start=PAGE*PSIZE, slice=rows.slice(start,start+PSIZE);
 cnt.textContent=`— ${rows.length} seller${rows.length===1?'':'s'}`+(f?` (of ${ALL.length})`:'');
 tb.innerHTML='';
 for(const s of slice){
  const tr=document.createElement('tr');
  let cells=`<td><b>${esc(s.store_name)||'(no store name)'}</b><div class=muted>${esc(s.business_name)}<br>${esc(s.seller_id)}</div></td>`;
  for(const m of MK){cells+=`<td id="c_${s.seller_id}_${m}">${stChip(s.status[m])}<br>
     <button onclick="verify('${s.seller_id}','${m}')">Verify</button>
     <button onclick="reject('${s.seller_id}','${m}')">Not on</button></td>`}
  tr.innerHTML=cells;tb.appendChild(tr);
 }
 document.getElementById('pg').textContent=rows.length?`${start+1}–${Math.min(start+PSIZE,rows.length)} of ${rows.length}`:'0 of 0';
 document.getElementById('prev').disabled=PAGE<=0;
 document.getElementById('next').disabled=PAGE>=pages-1;
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
   btn.onclick=()=>confirmStore(sid,m,c.store_url||"",c.seller_display,c.amazon_brand||"");   // closure: real values, no HTML-attr injection
   row.appendChild(info);row.appendChild(btn);box.appendChild(row);
 }
 const urow=document.createElement('div');urow.className='cand';
 const inp=document.createElement('input');inp.type='text';inp.id=`u_${sid}_${m}`;inp.placeholder='…or paste the correct store URL';
 const ubtn=document.createElement('button');ubtn.textContent='Confirm URL';ubtn.onclick=()=>confirmUrl(sid,m);
 urow.appendChild(inp);urow.appendChild(ubtn);box.appendChild(urow);
}
async function confirmStore(sid,m,url,disp,brand){
 await j('/api/confirm',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m,store_url:url,seller_display:disp,amazon_brand:brand||""})});load();}
async function confirmUrl(sid,m){
 const url=document.getElementById(`u_${sid}_${m}`).value.trim();if(!url)return;
 // Also carry the Naar store name: Amazon's structured API matches offers by the
 // Sold-by NAME (not a URL), so a URL-only confirm would never match live.
 const name=document.getElementById(`c_${sid}_${m}`).closest('tr').querySelector('b').textContent.trim();
 await j('/api/confirm',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m,store_url:url,seller_display:name})});load();}
async function reject(sid,m){await j('/api/reject',{method:'POST',body:JSON.stringify({seller_id:sid,marketplace:m})});load();}

// --- high-similarity auto-confirm sweep ---
let _sweepTimer=null;
async function sweepInit(){
 const st=await j('/api/autoconfirm/status');
 if(st.status==='running'){sweepRunning(st);sweepPoll();} else sweepPanel(st);
}
function sweepPanel(st){
 const p=document.getElementById('sweep_panel');
 const note = st&&st.status==='done' ? `<span class=muted>last sweep auto-confirmed ${st.confirmed} store(s)</span>`
   : (st&&st.status==='error' ? `<span class=muted>last sweep error: ${esc(st.error)}</span>` : '');
 p.innerHTML=`<button id=sweepbtn>⚡ Auto-confirm high-confidence (sim &gt; 0.9)</button> ${note}`;
 document.getElementById('sweepbtn').onclick=sweepPreview;
}
async function sweepPreview(){
 const pv=await j('/api/autoconfirm/preview');
 const p=document.getElementById('sweep_panel');
 p.innerHTML=`<div class=cands>Auto-confirm sweep will run store discovery on <b>${pv.pairs}</b> pending
   seller×marketplace pair(s) across <b>${pv.sellers}</b> sellers (~<b>${pv.api_calls_est}</b> ScraperAPI calls, paid),
   and confirm only exact/near-exact name matches (sim &gt; 0.9), tagged <i>auto</i>.
   <button id=sweepgo class=primary>Run sweep</button> <button id=sweepcancel>Cancel</button></div>`;
 document.getElementById('sweepcancel').onclick=()=>sweepPanel({status:'idle'});
 document.getElementById('sweepgo').onclick=async()=>{
   const r=await j('/api/autoconfirm',{method:'POST',body:'{}'});
   if(r&&r.error){p.innerHTML=`<span class=muted>${esc(r.error)}</span>`;setTimeout(()=>sweepPanel({status:'idle'}),1500);return;}
   sweepPoll();
 };
}
function sweepRunning(st){
 document.getElementById('sweep_panel').innerHTML=
   `<div class=cands>auto-confirm sweep running… <b>${st.done}</b> / <b>${st.total||'?'}</b> pair(s)</div>`;
}
function sweepPoll(){
 clearTimeout(_sweepTimer);
 _sweepTimer=setTimeout(async()=>{
   const st=await j('/api/autoconfirm/status');
   if(st.status==='running'){sweepRunning(st);sweepPoll();}
   else{sweepPanel(st);_sellers_cache_bust();}
 },1500);
}
function _sellers_cache_bust(){ /* reload seller statuses after a sweep changed them */ load(); }

document.getElementById('q').oninput=e=>{FILT=e.target.value;PAGE=0;render();};
document.getElementById('ps').onchange=e=>{PSIZE=parseInt(e.target.value,10)||25;PAGE=0;render();};
document.getElementById('prev').onclick=()=>{PAGE--;render();};
document.getElementById('next').onclick=()=>{PAGE++;render();};

// --- view toggle ---
function showView(v){
  document.getElementById('view_annotate').style.display = v==='annotate'?'':'none';
  document.getElementById('view_results').style.display  = v==='results'?'':'none';
  document.getElementById('tab_annotate').className = v==='annotate'?'primary':'';
  document.getElementById('tab_results').className  = v==='results'?'primary':'';
  if(v==='results') resultsInit();
}
document.getElementById('tab_annotate').onclick=()=>showView('annotate');
document.getElementById('tab_results').onclick=()=>showView('results');

// --- results state ---
let RPAGE=0, RPSIZE=25, RQ='', RSTATUS='';
let _pollTimer=null;

async function resultsInit(){
  const st=await j('/api/run/status');
  if(st.status==='running'){ renderRunning(st); pollRun(); }
  else { renderRunPanel(st); loadResults(); }
}
function renderRunPanel(st){
  const p=document.getElementById('run_panel');
  const note = st.status==='error' ? `<span class=muted>last run error: ${esc(st.error)}</span>` : '';
  p.innerHTML=`<button id=runbtn class=primary>Finalize &amp; run price match</button> ${note}`;
  document.getElementById('runbtn').onclick=previewRun;
}
async function previewRun(){
  const pv=await j('/api/run/preview');
  const p=document.getElementById('run_panel');
  p.innerHTML=`<div class=cands>Will check <b>${pv.products}</b> products across
    <b>${pv.sellers}</b> confirmed sellers (~<b>${pv.api_calls_est}</b> ScraperAPI calls, paid).
    <button id=go class=primary>Run</button> <button id=cancel>Cancel</button></div>`;
  document.getElementById('cancel').onclick=()=>renderRunPanel({status:'idle'});
  document.getElementById('go').onclick=async()=>{
    const r=await j('/api/run',{method:'POST',body:'{}'});
    if(r&&r.error){ p.innerHTML=`<span class=muted>${esc(r.error)}</span>`; renderRunPanel({status:'idle'}); return; }
    pollRun();
  };
}
function renderRunning(st){
  document.getElementById('run_panel').innerHTML=
    `<div class=cands>running price match… <b>${st.done}</b> / <b>${st.total||'?'}</b></div>`;
}
function pollRun(){
  clearTimeout(_pollTimer);
  _pollTimer=setTimeout(async()=>{
    const st=await j('/api/run/status');
    if(st.status==='running'){ renderRunning(st); pollRun(); }
    else { renderRunPanel(st); loadResults(); }
  },1500);
}
async function loadResults(){
  const url=`/api/results?status=${encodeURIComponent(RSTATUS)}&seller=${encodeURIComponent(RQ)}`
    +`&limit=${RPSIZE}&offset=${RPAGE*RPSIZE}`;
  const d=await j(url);
  const tb=document.querySelector('#rt tbody'); tb.innerHTML='';
  document.getElementById('dlcsv').href='/api/results/export.csv';
  const rows=d.rows||[];
  if(!rows.length){ tb.innerHTML='<tr><td colspan=9 class=muted>no results yet — run a price match</td></tr>'; }
  for(const r of rows){
    const naar=r.naar_selling_price, mkt=(r.marketplace_unit_price!=null?r.marketplace_unit_price:r.marketplace_selling_price);
    const delta=(naar!=null&&mkt!=null)?(mkt-naar):null;
    const dtxt=delta==null?'':(delta>=0?`+${delta.toFixed(2)}`:delta.toFixed(2));
    const dcol=delta==null?'':(delta<0?'#0a0':'#a00');
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${esc(r.naar_seller_name||r.naar_seller_id)}</td>
      <td>${esc(r.naar_product_title)} <span class=muted>${esc(r.naar_variant_name||'')}</span></td>
      <td>${esc(r.marketplace)}</td>
      <td>${naar!=null?naar.toFixed(2):''}</td>
      <td>${mkt!=null?mkt.toFixed(2):''}</td>
      <td style="color:${dcol}">${dtxt}</td>
      <td>${stChip((r.status||'').toLowerCase().slice(0,4))}${esc(r.status)}</td>
      <td>${esc(r.marketplace_sold_by||'')}</td>
      <td class=muted>${esc((r.other_sellers||'').slice(0,60))}</td>`;
    tb.appendChild(tr);
  }
  const total=d.total||0, start=RPAGE*RPSIZE;
  document.getElementById('rpg').textContent= total?`${start+1}–${Math.min(start+RPSIZE,total)} of ${total}`:'0';
  document.getElementById('rprev').disabled= RPAGE<=0;
  document.getElementById('rnext').disabled= start+RPSIZE>=total;
}
document.getElementById('rq').oninput=e=>{RQ=e.target.value;RPAGE=0;loadResults();};
document.getElementById('rstatus').onchange=e=>{RSTATUS=e.target.value;RPAGE=0;loadResults();};
document.getElementById('rprev').onclick=()=>{if(RPAGE>0){RPAGE--;loadResults();}};
document.getElementById('rnext').onclick=()=>{RPAGE++;loadResults();};

load();
sweepInit();
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
            if u.path == "/api/run/preview":
                plan = poc.confirmed_scan_plan(_catalogue(), list(MARKETPLACES))
                return self._send(200, json.dumps({k: plan[k] for k in
                    ("sellers", "products", "pairs", "api_calls_est")}))
            if u.path == "/api/run/status":
                with _job_lock:
                    return self._send(200, json.dumps(dict(_job)))
            if u.path == "/api/autoconfirm/preview":
                plan = poc.auto_confirm_plan(load_naar_sellers(), _adapters())
                return self._send(200, json.dumps({k: plan[k] for k in
                    ("sellers", "pairs", "api_calls_est")}))
            if u.path == "/api/autoconfirm/status":
                with _sweep_lock:
                    return self._send(200, json.dumps(dict(_sweep_job)))
            if u.path == "/api/results":
                q = parse_qs(u.query)
                def _q(name, default=""):
                    return (q.get(name) or [default])[0]
                run_id = _q("run_id")
                rows, total = results_store.query_results(
                    run_id=int(run_id) if run_id.isdigit() else None,
                    status=_q("status") or None, seller=_q("seller") or None,
                    order=_q("order", "matches_first"),
                    limit=_int(_q("limit", "50"), 50), offset=_int(_q("offset", "0"), 0))
                return self._send(200, json.dumps(
                    {"rows": rows, "total": total, "run": results_store.latest_run()}))
            if u.path == "/api/runs":
                return self._send(200, json.dumps(results_store.list_runs()))
            if u.path == "/api/results/export.csv":
                import csv as _csv
                import io as _io
                q = parse_qs(u.query)
                run_id = (q.get("run_id") or [""])[0]
                rows, _ = results_store.query_results(
                    run_id=int(run_id) if run_id.isdigit() else None, limit=100000)
                buf = _io.StringIO()
                w = _csv.DictWriter(buf, fieldnames=results_store.RESULT_COLS, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow(r)
                data = buf.getvalue().encode("utf-8-sig")
                self.send_response(200)
                self.send_header("content-type", "text/csv; charset=utf-8")
                self.send_header("content-disposition", 'attachment; filename="naar_price_match.csv"')
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
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
            if u.path == "/api/run":
                with _job_lock:
                    if _job["status"] == "running":
                        return self._send(409, json.dumps({"error": "a run is already in progress"}))
                    _job.update(status="running", done=0, total=0, run_id=None,
                                started=poc._now_iso(), error="")
                plan = poc.confirmed_scan_plan(_catalogue(), list(MARKETPLACES))
                with _job_lock:
                    _job["total"] = len(plan["plan"])
                if not plan["plan"]:
                    with _job_lock:
                        _job.update(status="error", error="no confirmed stores to run")
                    return self._send(400, json.dumps({"error": "no confirmed stores to run"}))
                threading.Thread(target=_run_scan_job, args=(plan["plan"],), daemon=True).start()
                return self._send(200, json.dumps({"started": True, "total": len(plan["plan"])}))
            if u.path == "/api/autoconfirm":
                with _sweep_lock:
                    if _sweep_job["status"] == "running":
                        return self._send(409, json.dumps({"error": "a sweep is already in progress"}))
                    _sweep_job.update(status="running", done=0, total=0, confirmed=0,
                                      started=poc._now_iso(), error="")
                plan = poc.auto_confirm_plan(load_naar_sellers(), _adapters())
                with _sweep_lock:
                    _sweep_job["total"] = len(plan["plan"])
                if not plan["plan"]:
                    with _sweep_lock:
                        _sweep_job.update(status="error", error="no pending stores to sweep")
                    return self._send(400, json.dumps({"error": "no pending stores to sweep"}))
                threading.Thread(target=_run_sweep_job, args=(plan["plan"],), daemon=True).start()
                return self._send(200, json.dumps({"started": True, "total": len(plan["plan"])}))
            if u.path == "/api/confirm":
                poc.confirm_store(body["seller_id"], body["marketplace"],
                                  body.get("store_url", ""), body.get("seller_display", ""),
                                  amazon_brand=body.get("amazon_brand", ""))
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
    # Load sellers in the background so the page is up instantly; the live
    # catalogue pages in over a few seconds and the UI fills itself in.
    threading.Thread(target=warm_sellers, daemon=True).start()
    print(f"Store verification ({src}) — loading sellers in background")
    print(f"Open http://127.0.0.1:{port}  (writes {poc._registry_path()})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
