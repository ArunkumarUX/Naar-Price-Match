"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobStatus, ResultRow } from "@/lib/types";
import { rupees } from "@/lib/format";

// Fixed marketplace columns (per the agreed layout). Only amazon_in has live data
// today; the others render "not available" until a provider is wired.
const COLS: { key: string; label: string }[] = [
  { key: "amazon_in", label: "Amazon" },
  { key: "flipkart", label: "Flipkart" },
  { key: "meesho", label: "Meesho" },
  { key: "noon", label: "Noon" },
];

type Cell = { price: number; pct: number | null } | null;
interface ProductRow { product: string; variant: string; naar: number | null; cells: Record<string, Cell>; }
interface SellerGroup { seller: string; products: ProductRow[]; markets: Set<string>; }

/** A priced cell exists only where we have a confirmed marketplace price (MATCHED). */
function cellFor(r: ResultRow): Cell {
  if (r.status !== "MATCHED") return null;
  const price = r.marketplace_unit_price ?? r.marketplace_selling_price;
  if (price == null) return null;
  const pct = r.naar_selling_price ? ((price - r.naar_selling_price) / r.naar_selling_price) * 100 : null;
  return { price, pct };
}

function group(rows: ResultRow[]): SellerGroup[] {
  const bySeller = new Map<string, SellerGroup>();
  const byProduct = new Map<string, ProductRow>();
  for (const r of rows) {
    const sName = r.naar_seller_name || r.naar_seller_id;
    let sg = bySeller.get(sName);
    if (!sg) { sg = { seller: sName, products: [], markets: new Set() }; bySeller.set(sName, sg); }
    const pKey = `${sName}|${r.naar_product_title}|${r.naar_variant_name}`;
    let pr = byProduct.get(pKey);
    if (!pr) {
      pr = { product: r.naar_product_title, variant: r.naar_variant_name, naar: r.naar_selling_price, cells: {} };
      byProduct.set(pKey, pr); sg.products.push(pr);
    }
    const cell = cellFor(r);
    if (cell) { pr.cells[r.marketplace] = cell; sg.markets.add(r.marketplace); }
  }
  return [...bySeller.values()].sort((a, b) => a.seller.localeCompare(b.seller));
}

export default function ResultsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");

  const query = useQuery({
    queryKey: ["results-all"],
    queryFn: () => api.results({ limit: 5000 }),
    placeholderData: (p) => p,
  });
  const rows = query.data?.rows ?? [];
  const run = query.data?.run ?? null;
  const refresh = () => qc.invalidateQueries({ queryKey: ["results-all"] });

  const groups = useMemo(() => {
    const g = group(rows);
    const f = q.trim().toLowerCase();
    return f ? g.filter((s) => s.seller.toLowerCase().includes(f) ||
      s.products.some((p) => p.product.toLowerCase().includes(f))) : g;
  }, [rows, q]);

  return (
    <div>
      <RunPanel onDone={refresh} />

      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <div className="flex flex-1 items-center gap-2 rounded-pill border px-3.5 py-2"
             style={{ borderColor: "var(--line)", background: "var(--panel)", minWidth: 220 }}>
          <input className="w-full bg-transparent outline-none" style={{ color: "var(--ink)" }}
                 placeholder="Search seller or product" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <span className="text-[13px]" style={{ color: "var(--ink-3)" }}>{groups.length} sellers</span>
        <div className="flex-1" />
        <a href={api.exportCsvUrl()} className="rounded-pill px-3.5 py-1.5 text-[13px] font-bold"
           style={{ background: "#00B3C2", color: "#02201f" }}>Download CSV</a>
      </div>

      <div className="overflow-hidden rounded-brand border" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--ink-3)", background: "var(--panel-2)", borderBottom: "1px solid var(--line)" }}>
                  Seller / Product
                </th>
                <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--ink-3)", background: "var(--panel-2)", borderBottom: "1px solid var(--line)", whiteSpace: "nowrap" }}>
                  Naar ₹
                </th>
                {COLS.map((c) => (
                  <th key={c.key} className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--ink-3)", background: "var(--panel-2)", borderBottom: "1px solid var(--line)", whiteSpace: "nowrap" }}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.isError && (
                <tr><td colSpan={2 + COLS.length} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>{(query.error as Error).message}</td></tr>
              )}
              {!query.isError && groups.length === 0 && (
                <tr><td colSpan={2 + COLS.length} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>no results yet — run a price match</td></tr>
              )}
              {groups.map((sg) => <SellerBlock key={sg.seller} group={sg} />)}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 text-[13px]" style={{ color: "var(--ink-3)" }}>
        {run ? `run #${run.id} · ${run.finished_at?.slice(0, 16).replace("T", " ")}` : "no run yet"}
        {" · a price shows only where a marketplace store is confirmed to sell the same product; % is vs the Naar price"}
      </div>
    </div>
  );
}

function SellerBlock({ group }: { group: SellerGroup }) {
  const [open, setOpen] = useState(true);
  const priced = group.products.filter((p) => Object.keys(p.cells).length > 0).length;
  const marketLabels = COLS.filter((c) => group.markets.has(c.key)).map((c) => c.label);
  return (
    <>
      <tr style={{ borderBottom: "1px solid var(--line)", cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <td className="px-4 py-3" colSpan={2 + COLS.length} style={{ background: "var(--panel-2)" }}>
          <div className="flex items-center gap-2">
            <span style={{ color: "var(--ink-3)", width: 14, display: "inline-block" }}>{open ? "▾" : "▸"}</span>
            <span className="font-semibold">{group.seller}</span>
            <span className="text-xs" style={{ color: "var(--ink-3)" }}>
              · {group.products.length} products · {priced} priced
              {marketLabels.length ? ` · ${marketLabels.join(", ")}` : " · no marketplace prices"}
            </span>
          </div>
        </td>
      </tr>
      {open && group.products.map((p, i) => (
        <tr key={i} style={{ borderBottom: "1px solid var(--line-2)" }}>
          <td className="px-4 py-3 pl-9">
            <div style={{ color: "var(--ink-2)" }}>{p.product}</div>
            {p.variant && p.variant !== "-" && <div className="text-xs" style={{ color: "var(--ink-3)" }}>{p.variant}</div>}
          </td>
          <td className="px-4 py-3 text-right tnum font-semibold">{rupees(p.naar)}</td>
          {COLS.map((c) => {
            const cell = p.cells[c.key];
            if (!cell) return <td key={c.key} className="px-4 py-3 text-right text-xs" style={{ color: "var(--ink-3)" }}>not available</td>;
            const good = cell.pct != null && cell.pct > 0; // marketplace pricier => Naar cheaper
            return (
              <td key={c.key} className="px-4 py-3 text-right">
                <div className="tnum font-semibold">{rupees(cell.price)}</div>
                {cell.pct != null && (
                  <div className="tnum text-xs" style={{ color: good ? "var(--good)" : "var(--high)" }}>
                    {cell.pct > 0 ? "+" : ""}{cell.pct.toFixed(0)}%
                  </div>
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
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
