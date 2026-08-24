"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, MARKETS } from "@/lib/api";
import type { Candidate, Seller } from "@/lib/types";
import StatusPill from "@/components/StatusPill";
import SweepPanel from "@/components/SweepPanel";

const PAGE = 25;

export default function AnnotatePage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null); // `${sid}:${mkt}`

  const sellersQ = useQuery({
    queryKey: ["sellers"],
    queryFn: api.sellers,
    refetchInterval: (query) =>
      query.state.data && !Array.isArray(query.state.data) && "loading" in query.state.data ? 2000 : false,
  });

  const data = sellersQ.data;
  const loading = data && !Array.isArray(data) && "loading" in data;
  const error = data && !Array.isArray(data) && "error" in data ? data.error : sellersQ.error?.message;
  const sellers: Seller[] = Array.isArray(data) ? data : [];

  const filtered = useMemo(() => {
    const f = q.trim().toLowerCase();
    return f
      ? sellers.filter((s) => (s.store_name + " " + s.business_name + " " + s.seller_id).toLowerCase().includes(f))
      : sellers;
  }, [sellers, q]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const pg = Math.min(page, pages - 1);
  const slice = filtered.slice(pg * PAGE, pg * PAGE + PAGE);
  const refresh = () => qc.invalidateQueries({ queryKey: ["sellers"] });

  return (
    <div>
      <SweepPanel onDone={refresh} />

      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <div className="flex flex-1 items-center gap-2 rounded-pill border px-3.5 py-2"
             style={{ borderColor: "var(--line)", background: "var(--panel)", minWidth: 220 }}>
          <input
            className="w-full bg-transparent outline-none"
            style={{ color: "var(--ink)" }}
            placeholder="Search seller / business / id"
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(0); }}
          />
        </div>
        <span className="text-[13px]" style={{ color: "var(--ink-3)" }}>
          {loading ? "loading sellers…" : `${filtered.length} sellers`}
        </span>
        <div className="flex-1" />
        <Pager pg={pg} pages={pages} total={filtered.length} setPage={setPage} />
      </div>

      <div className="overflow-hidden rounded-brand border" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse" style={{ minWidth: 720 }}>
            <thead>
              <tr>
                {["Seller (Naar)", "Amazon", "Flipkart", "Meesho"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider"
                      style={{ color: "var(--ink-3)", background: "var(--panel-2)", borderBottom: "1px solid var(--line)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {error && (
                <tr><td colSpan={4} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>
                  could not load sellers: {error}
                </td></tr>
              )}
              {!error && loading && (
                <tr><td colSpan={4} className="px-4 py-10 text-center" style={{ color: "var(--ink-3)" }}>loading…</td></tr>
              )}
              {!error && !loading && slice.map((s) => (
                <tr key={s.seller_id} style={{ borderBottom: "1px solid var(--line-2)" }}>
                  <td className="px-4 py-3 align-top">
                    <div className="font-semibold">{s.store_name || "(no store name)"}</div>
                    <div className="text-xs" style={{ color: "var(--ink-3)" }}>{s.business_name}</div>
                    <div className="text-xs" style={{ color: "var(--ink-3)" }}>{s.seller_id}</div>
                  </td>
                  {MARKETS.map((m) => (
                    <td key={m.key} className="px-4 py-3 align-top">
                      <StatusPill status={s.status[m.key]} />
                      <MarketCell
                        seller={s}
                        marketplace={m.key}
                        openKey={open}
                        setOpen={setOpen}
                        onChange={refresh}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Pager({ pg, pages, total, setPage }: { pg: number; pages: number; total: number; setPage: (n: number) => void }) {
  const start = pg * PAGE;
  return (
    <div className="flex items-center gap-2 text-[13px]" style={{ color: "var(--ink-3)" }}>
      <button className="rounded-pill border px-3 py-1.5 disabled:opacity-40" style={{ borderColor: "var(--line)", background: "var(--panel)" }}
              disabled={pg <= 0} onClick={() => setPage(pg - 1)}>‹ Prev</button>
      <span className="tnum">{total ? `${start + 1}–${Math.min(start + PAGE, total)} of ${total}` : "0"}</span>
      <button className="rounded-pill border px-3 py-1.5 disabled:opacity-40" style={{ borderColor: "var(--line)", background: "var(--panel)" }}
              disabled={pg >= pages - 1} onClick={() => setPage(pg + 1)}>Next ›</button>
    </div>
  );
}

function MarketCell({
  seller, marketplace, openKey, setOpen, onChange,
}: {
  seller: Seller; marketplace: "amazon_in" | "flipkart" | "meesho";
  openKey: string | null; setOpen: (k: string | null) => void; onChange: () => void;
}) {
  const key = `${seller.seller_id}:${marketplace}`;
  const isOpen = openKey === key;
  const [cands, setCands] = useState<Candidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [url, setUrl] = useState("");

  async function verify() {
    setOpen(key); setBusy(true); setErr(""); setCands(null);
    try {
      const r = await api.propose(seller.seller_id, marketplace);
      if (Array.isArray(r)) setCands(r);
      else setErr(r.error);
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }
  async function confirm(store_url: string, seller_display: string) {
    await api.confirm({ seller_id: seller.seller_id, marketplace, store_url, seller_display });
    setOpen(null); onChange();
  }
  async function reject() {
    await api.reject({ seller_id: seller.seller_id, marketplace }); onChange();
  }

  return (
    <div className="mt-1.5">
      <div className="flex gap-1.5">
        <MiniBtn onClick={verify}>Verify</MiniBtn>
        <MiniBtn onClick={reject}>Not on</MiniBtn>
      </div>
      {isOpen && (
        <div className="mt-1.5 rounded-[10px] border p-2.5" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
          {busy && <div className="text-xs" style={{ color: "var(--ink-3)" }}>searching…</div>}
          {err && <div className="text-xs" style={{ color: "var(--ink-3)" }}>could not search: {err}</div>}
          {cands && cands.length === 0 && <div className="text-xs" style={{ color: "var(--ink-3)" }}>no candidate sellers found</div>}
          {cands?.map((c, i) => (
            <div key={i} className="flex items-center justify-between gap-2 border-b py-1.5" style={{ borderColor: "var(--line-2)" }}>
              <div className="text-[13px]">
                {c.seller_display}{" "}
                <span className="text-xs" style={{ color: "var(--ink-3)" }}>
                  (sim {c.similarity}{c.n_products ? ` · ${c.n_products} products` : ""})
                </span>
              </div>
              <button className="rounded-md px-2.5 py-1 text-xs font-bold" style={{ background: "#00B3C2", color: "#02201f" }}
                      onClick={() => confirm(c.store_url || "", c.seller_display)}>Confirm</button>
            </div>
          ))}
          <div className="mt-1.5 flex gap-1.5">
            <input className="flex-1 rounded-md border px-2 py-1 text-xs outline-none"
                   style={{ borderColor: "var(--line)", background: "var(--panel)", color: "var(--ink)" }}
                   placeholder="…or paste the correct store URL" value={url} onChange={(e) => setUrl(e.target.value)} />
            <MiniBtn onClick={() => url.trim() && confirm(url.trim(), seller.store_name)}>Confirm URL</MiniBtn>
          </div>
        </div>
      )}
    </div>
  );
}

function MiniBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="rounded-md border px-2.5 py-1 text-xs"
      style={{ borderColor: "var(--line)", background: "var(--panel)", color: "var(--ink-2)" }}>
      {children}
    </button>
  );
}
