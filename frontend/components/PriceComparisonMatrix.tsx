"use client";

import { useState } from "react";
import { useComparisonMatrix, useSellers, type ComparisonProduct } from "@/lib/api";
import { parityStatus } from "@/lib/brand";

function PriceCell({ price, status, label }: { price: number | null; status: string; label?: string }) {
  const style = parityStatus[status as keyof typeof parityStatus] || parityStatus.missing;
  if (!price) return <span className="text-naar-warm text-sm">—</span>;
  return (
    <div className="text-right">
      <div className="font-extrabold tabular-nums text-forest">₹{price.toLocaleString("en-IN")}</div>
      <span className={`inline-block mt-1.5 text-[10px] font-bold px-2.5 py-0.5 rounded-pill ${style.bg} ${style.text}`}>
        {label || style.label}
      </span>
    </div>
  );
}

function ProductComparisonCard({ product }: { product: ComparisonProduct }) {
  const [expanded, setExpanded] = useState(false);
  const { channels, summary } = product;
  const sellers = channels.sellers || [];

  return (
    <div className="naar-card overflow-hidden">
      <div className="p-5 border-b border-naar-mist bg-sandstone/50">
        <div className="flex flex-wrap justify-between gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">{product.sku}</p>
            <h3 className="font-extrabold text-lg text-forest mt-0.5">{product.name}</h3>
            <p className="text-sm text-naar-slate">{product.variant}</p>
          </div>
          <div className="text-right">
            <p className="naar-eyebrow justify-end mb-1">Naar Price</p>
            <p className="text-2xl font-extrabold text-forest tabular-nums">₹{product.naar_price.toLocaleString("en-IN")}</p>
            {summary?.lowest_competitor && (
              <p className="text-xs text-naar-warm mt-1">
                Lowest: ₹{summary.lowest_competitor.price?.toLocaleString("en-IN")} · {summary.lowest_competitor.source}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-naar-mist">
        {(["amazon", "flipkart", "meesho"] as const).map((platform) => {
          const ch = channels[platform];
          return (
            <div key={platform} className="p-4 bg-white">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-naar-warm mb-3">{platform}</p>
              <PriceCell price={ch?.price ?? null} status={ch?.status || "missing"} label={ch?.label} />
              {ch?.url && (
                <a href={ch.url} target="_blank" rel="noreferrer" className="text-[10px] text-turquoise-dim font-bold mt-2 inline-block hover:underline">
                  {ch.url.includes("/search") || ch.url.includes("/s?") ? "Search →" : "View →"}
                </a>
              )}
            </div>
          );
        })}
        <div className="p-4 bg-turquoise/6">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-naar-warm mb-3">Sellers ({sellers.length})</p>
          {summary?.best_seller ? (
            <>
              <PriceCell
                price={summary.best_seller.price ?? null}
                status={summary.best_seller.status}
                label={summary.best_seller.label}
              />
              <p className="text-[10px] text-naar-slate mt-1 truncate font-semibold" title={summary.best_seller.seller_name}>
                {summary.best_seller.seller_name}
              </p>
            </>
          ) : (
            <span className="text-naar-warm text-sm">No matches</span>
          )}
          {sellers.length > 1 && (
            <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-turquoise-dim font-bold mt-2 hover:underline">
              {expanded ? "Hide sellers" : `+${sellers.length - 1} more`}
            </button>
          )}
        </div>
      </div>

      {expanded && sellers.length > 0 && (
        <div className="border-t border-naar-mist divide-y divide-naar-mist bg-cloud/50">
          {sellers.map((s, i) => (
            <div key={i} className="px-5 py-3 flex items-center justify-between gap-4 text-sm">
              <div className="min-w-0">
                <p className="font-bold text-forest truncate">{s.seller_name}</p>
                <p className="text-[10px] text-naar-warm">{s.seller_category}</p>
              </div>
              <PriceCell price={s.price ?? null} status={s.status} label={s.label} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PriceComparisonMatrix() {
  const { data, isLoading, isError, error, refetch, isFetching } = useComparisonMatrix();
  const { data: sellerData } = useSellers();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="naar-eyebrow">Price Intelligence</div>
          <h2 className="text-xl font-extrabold text-forest">Naar vs Competitors</h2>
          <p className="text-sm text-naar-slate mt-1">
            {sellerData?.count ?? 0} seller websites · Amazon · Flipkart · Meesho
          </p>
        </div>
        <button onClick={() => refetch()} disabled={isFetching} className="btn-naar-secondary">
          {isFetching ? "Refreshing…" : "↻ Refresh"}
        </button>
      </div>

      {isError && (
        <div className="naar-card px-4 py-3 text-sm border-naar-red/30 bg-naar-red/8 text-forest">
          Could not reach the API — {error instanceof Error ? error.message : "connection failed"}.
          Restart with <code className="text-xs">scripts/restart-dev.sh</code> and ensure the backend is on port 8000.
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-naar-warm">Loading price comparison…</div>
      ) : (
        <div className="space-y-4">
          {(data?.products || []).map((p) => (
            <ProductComparisonCard key={p.sku} product={p} />
          ))}
          {!data?.products?.length && (
            <div className="text-center py-16 text-naar-warm border border-dashed border-naar-pebble rounded-naar bg-white/50">
              No comparison data — run a scan first
            </div>
          )}
        </div>
      )}
    </div>
  );
}
