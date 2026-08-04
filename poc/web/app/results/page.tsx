"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobStatus, ResultsResponse } from "@/lib/types";
import { rupees, delta, deltaText } from "@/lib/format";
import StatusPill from "@/components/StatusPill";

const STATUSES = ["", "MATCHED", "PRODUCT_NOT_FOUND", "OUT_OF_STOCK", "SOURCE_ERROR"];
const LABEL: Record<string, string> = {
  "": "All", MATCHED: "Matched", PRODUCT_NOT_FOUND: "Not found", OUT_OF_STOCK: "Out of stock", SOURCE_ERROR: "Error",
};
const PAGE = 25;

export default function ResultsPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [seller, setSeller] = useState("");
  const [page, setPage] = useState(0);

  const q = useQuery<ResultsResponse>({
    queryKey: ["results", status, seller, page],
    queryFn: () => api.results({ status, seller, limit: PAGE, offset: page * PAGE }),
    placeholderData: (p) => p,
  });
  const rows = q.data?.rows ?? [];
  const total = q.data?.total ?? 0;
  const run = q.data?.run ?? null;
  const refresh = () => qc.invalidateQueries({ queryKey: ["results"] });

  return (
    <div>
      <RunPanel onDone={refresh} />

      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <div className="flex flex-1 items-center gap-2 rounded-pill border px-3.5 py-2"
             style={{ borderColor: "var(--line)", background: "var(--panel)", minWidth: 200 }}>
          <input className="w-full bg-transparent outline-none" style={{ color: "var(--ink)" }}
                 placeholder="Filter by seller" value={seller}
                 onChange={(e) => { setSeller(e.target.value); setPage(0); }} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => { setStatus(s); setPage(0); }}
              className="rounded-pill border px-3 py-1.5 text-[13px]"
              style={{
                borderColor: status === s ? "var(--ink)" : "var(--line)",
                background: status === s ? "var(--ink)" : "var(--panel)",
                color: status === s ? "var(--bg)" : "var(--ink-2)",
              }}>
              {LABEL[s]}
            </button>
          ))}
        </div>
        <a href={api.exportCsvUrl()} className="rounded-pill px-3.5 py-1.5 text-[13px] font-bold"
           style={{ background: "#00B3C2", color: "#02201f" }}>Download CSV</a>
      </div>

      <div className="overflow-hidden rounded-brand border" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse" style={{ minWidth: 860 }}>
            <thead>
              <tr>
                {["Seller", "Product", "Market", "Naar ₹", "Market ₹", "Δ vs Naar", "Status", "Sold by", "Also sold by"].map((h, i) => (
                  <th key={h} className={`px-4 py-3 text-[11px] font-semibold uppercase tracking-wider ${i >= 3 && i <= 5 ? "text-right" : "text-left"}`}
                      style={{ color: "var(--ink-3)", background: "var(--panel-2)", borderBottom: "1px solid var(--line)", whiteSpace: "nowrap" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.isError && (
                <tr><td colSpan={9} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>{(q.error as Error).message}</td></tr>
              )}
              {!q.isError && rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>no results yet — run a price match</td></tr>
              )}
              {rows.map((r, i) => {
                const d = delta(r);
                const mkt = r.marketplace_unit_price ?? r.marketplace_selling_price;
                return (
                  <tr key={i} style={{ borderBottom: "1px solid var(--line-2)" }}>
                    <td className="px-4 py-3 font-semibold">{r.naar_seller_name || r.naar_seller_id}</td>
                    <td className="px-4 py-3">
                      <div style={{ color: "var(--ink-2)" }}>{r.naar_product_title}</div>
                      <div className="text-xs" style={{ color: "var(--ink-3)" }}>{r.naar_variant_name}</div>
                    </td>
                    <td className="px-4 py-3 text-xs capitalize" style={{ color: "var(--ink-3)" }}>{r.marketplace.replace("_in", "")}</td>
                    <td className="px-4 py-3 text-right tnum font-semibold">{rupees(r.naar_selling_price)}</td>
                    <td className="px-4 py-3 text-right tnum font-semibold">{rupees(mkt)}</td>
                    <td className="px-4 py-3 text-right tnum font-bold"
                        style={{ color: d == null ? "var(--ink-3)" : d > 0 ? "var(--good)" : "var(--high)" }}>
                      {deltaText(d)}
                    </td>
                    <td className="px-4 py-3"><StatusPill status={r.status} /></td>
                    <td className="px-4 py-3">{r.marketplace_sold_by || <span style={{ color: "var(--ink-3)" }}>—</span>}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--ink-3)", maxWidth: 200 }}>{r.other_sellers || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-[13px]" style={{ color: "var(--ink-3)" }}>
        <span>{run ? `run #${run.id} · ${run.finished_at?.slice(0, 16).replace("T", " ")}` : "no run yet"}</span>
        <div className="flex items-center gap-2">
          <button className="rounded-pill border px-3 py-1.5 disabled:opacity-40" style={{ borderColor: "var(--line)", background: "var(--panel)" }}
                  disabled={page <= 0} onClick={() => setPage(page - 1)}>‹ Prev</button>
          <span className="tnum">{total ? `${page * PAGE + 1}–${Math.min((page + 1) * PAGE, total)} of ${total}` : "0"}</span>
          <button className="rounded-pill border px-3 py-1.5 disabled:opacity-40" style={{ borderColor: "var(--line)", background: "var(--panel)" }}
                  disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next ›</button>
        </div>
      </div>
    </div>
  );
}

function RunPanel({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<"idle" | "preview" | "running" | "done" | "error">("idle");
  const [preview, setPreview] = useState<{ sellers: number; products: number; api_calls_est: number } | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [msg, setMsg] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.runStatus().then((st) => { if (st.status === "running") { setPhase("running"); poll(); } });
    return () => { if (timer.current) clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function poll() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const st = await api.runStatus();
      setJob(st);
      if (st.status === "running") { setPhase("running"); poll(); }
      else { setPhase(st.status === "error" ? "error" : "done"); setMsg(st.error || ""); onDone(); }
    }, 1500);
  }
  async function openPreview() { setPhase("preview"); setPreview(await api.runPreview()); }
  async function run() {
    try { await api.run(); setPhase("running"); poll(); }
    catch (e) { setPhase("error"); setMsg((e as Error).message); }
  }

  return (
    <div className="mb-4 rounded-brand border p-3" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
      {phase === "idle" && (
        <button className="rounded-pill px-3.5 py-1.5 text-sm font-bold" style={{ background: "#00B3C2", color: "#02201f" }} onClick={openPreview}>
          Finalize &amp; run price match
        </button>
      )}
      {phase === "preview" && preview && (
        <div className="text-sm">
          Will check <b>{preview.products}</b> products across <b>{preview.sellers}</b> confirmed sellers
          (~<b>{preview.api_calls_est}</b> ScraperAPI calls, paid).
          <div className="mt-2 flex gap-2">
            <button className="rounded-pill px-3.5 py-1.5 text-sm font-bold" style={{ background: "#00B3C2", color: "#02201f" }} onClick={run}>Run</button>
            <button className="rounded-pill border px-3.5 py-1.5 text-sm" style={{ borderColor: "var(--line)" }} onClick={() => setPhase("idle")}>Cancel</button>
          </div>
        </div>
      )}
      {phase === "running" && (
        <div className="text-sm">running price match… <b className="tnum">{job?.done ?? 0}</b> / <b className="tnum">{job?.total ?? "?"}</b></div>
      )}
      {phase === "done" && (
        <button className="rounded-pill px-3.5 py-1.5 text-sm font-bold" style={{ background: "#00B3C2", color: "#02201f" }} onClick={openPreview}>
          Re-run price match
        </button>
      )}
      {phase === "error" && (
        <div className="text-sm" style={{ color: "var(--err)" }}>{msg}
          <button className="ml-2 underline" onClick={() => setPhase("idle")}>dismiss</button>
        </div>
      )}
    </div>
  );
}
