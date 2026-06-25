"use client";

import { useComparisonMatrix, useRunScan, useScanStatus, useSellers, type ComparisonProduct } from "@/lib/api";
import { parityStatus } from "@/lib/brand";
import { normalizeNaarProductUrl } from "@/lib/naar-url";

const PLATFORMS = [
  { key: "naar" as const, label: "Naar" },
  { key: "amazon" as const, label: "Amazon" },
  { key: "flipkart" as const, label: "Flipkart" },
  { key: "meesho" as const, label: "Meesho" },
  { key: "sellers" as const, label: "Sellers" },
];

function formatInr(n: number | null | undefined) {
  if (n == null || n <= 0) return "—";
  return `₹${n.toLocaleString("en-IN")}`;
}

function deltaPct(naar: number, comp: number | null | undefined) {
  if (!comp || comp <= 0 || !naar) return null;
  return ((naar - comp) / naar) * 100;
}

function PriceBadge({ status, label }: { status: string; label?: string }) {
  const style = parityStatus[status as keyof typeof parityStatus] || parityStatus.missing;
  return (
    <span className={`inline-block text-[9px] font-bold px-2 py-0.5 rounded-pill ${style.bg} ${style.text}`}>
      {label || style.label}
    </span>
  );
}

function ShopRow({ product }: { product: ComparisonProduct }) {
  const { channels, summary } = product;
  const sellers = channels.sellers || [];
  const bestSeller = summary?.best_seller;
  const lowest = summary?.lowest_competitor;
  const naarShopUrl = normalizeNaarProductUrl(product.naar_url, product.name);

  const cells: Record<string, { price: number | null; status: string; label?: string; url?: string; sub?: string }> = {
    naar: { price: product.naar_price, status: "ok", label: "Naar shop", url: naarShopUrl },
    amazon: {
      price: channels.amazon?.price ?? null,
      status: channels.amazon?.status || "missing",
      label: channels.amazon?.label,
      url: channels.amazon?.url || undefined,
    },
    flipkart: {
      price: channels.flipkart?.price ?? null,
      status: channels.flipkart?.status || "missing",
      label: channels.flipkart?.label,
      url: channels.flipkart?.url || undefined,
    },
    meesho: {
      price: channels.meesho?.price ?? null,
      status: channels.meesho?.status || "missing",
      label: channels.meesho?.label,
      url: channels.meesho?.url || undefined,
    },
    sellers: {
      price: bestSeller?.price ?? null,
      status: bestSeller?.status || (sellers.length ? "missing" : "missing"),
      label: bestSeller?.label,
      url: bestSeller?.url || undefined,
      sub: bestSeller?.seller_name || (sellers.length ? `${sellers.length} matched` : undefined),
    },
  };

  return (
    <tr className="border-t border-naar-mist hover:bg-sandstone/30 transition-colors">
      <td className="px-4 py-4 align-top min-w-[220px]">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-naar-warm">{product.sku}</p>
        <p className="font-extrabold text-forest mt-0.5 leading-snug">{product.name}</p>
        {product.variant && <p className="text-xs text-naar-slate mt-0.5">{product.variant}</p>}
        <a
          href={naarShopUrl}
          target="_blank"
          rel="noreferrer"
          title="Product detail pages are in the Naar app. This opens the web shop."
          className="text-[10px] text-turquoise-dim font-bold mt-2 inline-block hover:underline"
        >
          Browse Naar Shop →
        </a>
      </td>
      {PLATFORMS.map((p) => {
        const cell = cells[p.key];
        const isNaar = p.key === "naar";
        const d = !isNaar ? deltaPct(product.naar_price, cell.price) : null;
        return (
          <td
            key={p.key}
            className={`px-3 py-4 align-top text-right ${isNaar ? "bg-turquoise/8 border-l border-r border-turquoise/20" : ""}`}
          >
            <p className={`font-extrabold tabular-nums ${isNaar ? "text-xl text-forest" : "text-forest"}`}>
              {formatInr(cell.price)}
            </p>
            {!isNaar && <PriceBadge status={cell.status} label={cell.label} />}
            {isNaar && (
              <p className="text-[9px] font-bold uppercase tracking-wider text-turquoise-dim mt-1">naar.io/shop</p>
            )}
            {d != null && (
              <p className={`text-[10px] font-bold mt-1 ${d > 0 ? "text-naar-red" : "text-naar-green"}`}>
                {d > 0 ? "−" : "+"}
                {Math.abs(d).toFixed(0)}% vs Naar
              </p>
            )}
            {cell.sub && <p className="text-[10px] text-naar-warm mt-1 truncate max-w-[120px] ml-auto">{cell.sub}</p>}
            {cell.url && (
              <a href={cell.url} target="_blank" rel="noreferrer" className="text-[9px] text-turquoise-dim font-bold hover:underline block mt-1">
                {cell.url.includes("/search") || cell.url.includes("/s?") || !cell.price ? "Search →" : "View →"}
              </a>
            )}
          </td>
        );
      })}
      <td className="px-3 py-4 align-top text-right text-xs">
        {lowest?.price ? (
          <>
            <p className="font-bold text-forest tabular-nums">{formatInr(lowest.price)}</p>
            <p className="text-naar-warm capitalize mt-0.5">{lowest.source}</p>
          </>
        ) : (
          <span className="text-naar-warm">—</span>
        )}
      </td>
    </tr>
  );
}

export function NaarShopCompareTable() {
  const { data, isLoading, isError, error, refetch, isFetching } = useComparisonMatrix();
  const { data: sellerData } = useSellers();
  const { data: scanStatus } = useScanStatus();
  const runScan = useRunScan();

  const hasCompetitorData = (data?.products || []).some((p) => {
    const c = p.channels;
    return Boolean(
      c.amazon?.price ||
        c.flipkart?.price ||
        c.meesho?.price ||
        c.amazon?.url ||
        c.flipkart?.url ||
        c.meesho?.url ||
        (c.sellers && c.sellers.length > 0),
    );
  });

  return (
    <div className="space-y-4">
      <div className="naar-card-dark p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="naar-eyebrow text-turquoise">naar.io/shop</div>
          <h2 className="text-xl font-extrabold text-cloud font-display">Exact price parity check</h2>
          <p className="text-sm text-cloud/55 mt-1">
            Every product on{" "}
            <a href="https://naar.io/shop" className="text-turquoise font-semibold hover:underline" target="_blank" rel="noreferrer">
              Naar Shop
            </a>{" "}
            vs Amazon · Flipkart · Meesho · {sellerData?.count ?? 0} seller sites
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <button onClick={() => refetch()} disabled={isFetching} className="btn-naar-secondary shrink-0">
            {isFetching ? "Refreshing…" : "↻ Refresh"}
          </button>
          <button
            onClick={() => runScan.mutate()}
            disabled={runScan.isPending}
            className="btn-naar-primary shrink-0"
          >
            {runScan.isPending ? "Starting scan…" : "▶ Run competitor scan"}
          </button>
        </div>
      </div>

      {runScan.isSuccess && (
        <div className="naar-card px-4 py-3 text-sm border-turquoise/30 bg-turquoise/8 text-forest">
          {runScan.data?.message ||
            "Competitor scan started. Amazon/Flipkart/Meesho links appear within ~1 minute; live prices may take longer."}
        </div>
      )}

      {scanStatus?.phase === "running" && (
        <div className="naar-card px-4 py-3 text-sm border-turquoise/30 bg-turquoise/8 text-forest">
          Scanning competitors… {scanStatus.scanned}/{scanStatus.total} products processed. Refresh to see new links.
        </div>
      )}

      {scanStatus?.phase === "failed" && (
        <div className="naar-card px-4 py-3 text-sm border-naar-red/30 bg-naar-red/8 text-forest">
          Last scan failed: {scanStatus.error || "unknown error"}
        </div>
      )}

      {!isLoading && data?.products?.length && !hasCompetitorData && (
        <div className="naar-card px-4 py-3 text-sm border-naar-honey/30 bg-naar-honey/10 text-forest">
          <strong>Naar prices are loaded</strong>, but competitor columns are empty until you run a scan. Click{" "}
          <strong>Run competitor scan</strong> above — search links appear within about a minute; live prices can take longer on Render.
        </div>
      )}

      {isError && (
        <div className="naar-card px-4 py-3 text-sm border-naar-red/30 bg-naar-red/8 text-forest">
          Could not load comparison — {error instanceof Error ? error.message : "API unavailable"}
        </div>
      )}

      <div className="naar-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="bg-sandstone/80 text-left">
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-[0.14em] text-naar-slate">Product</th>
                {PLATFORMS.map((p) => (
                  <th
                    key={p.key}
                    className={`px-3 py-3 text-[10px] font-bold uppercase tracking-[0.14em] text-right ${
                      p.key === "naar" ? "text-turquoise-dim bg-turquoise/10" : "text-naar-slate"
                    }`}
                  >
                    {p.label}
                  </th>
                ))}
                <th className="px-3 py-3 text-[10px] font-bold uppercase tracking-[0.14em] text-naar-slate text-right">
                  Lowest
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-16 text-center text-naar-warm">
                    Loading Naar shop comparison…
                  </td>
                </tr>
              ) : (
                (data?.products || []).map((p) => <ShopRow key={p.sku} product={p} />)
              )}
              {!isLoading && !data?.products?.length && (
                <tr>
                  <td colSpan={7} className="px-4 py-16 text-center text-naar-warm space-y-2">
                    <p>No products in database yet.</p>
                    <p className="text-sm">
                      Click <strong>Run competitor scan</strong> above to fetch Amazon, Flipkart and Meesho prices.
                    </p>
                    <p className="text-xs">
                      If sync fails, set <code>NAAR_CATALOG_API</code> in the project <code>.env</code> (or Render env) and run <strong>Sync Naar Catalog</strong>.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
