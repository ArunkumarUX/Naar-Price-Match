"use client";

import { NaarShopCompareTable } from "@/components/NaarShopCompareTable";
import { PriceComparisonMatrix } from "@/components/PriceComparisonMatrix";
import { PageHeader } from "@/components/PageHeader";
import { useRunScan, useScanStatus, useSellers } from "@/lib/api";
import { useEffect, useMemo, useState } from "react";

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

function normalizeSearch(s: string) {
  return s.trim().toLowerCase();
}

export default function ComparePage() {
  const { data: sellers } = useSellers();
  const isMobile = useMediaQuery("(max-width: 1023px)");

  const [search, setSearch] = useState("");
  const [onlyMismatches, setOnlyMismatches] = useState(false);

  const normalizedSearch = useMemo(() => normalizeSearch(search), [search]);

  const runScan = useRunScan();
  const scanStatus = useScanStatus();

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-8 pb-12">
      <PageHeader
        eyebrow="naar.io/shop · Price Parity"
        title="Naar Shop vs Competitors"
        description={`Exact price check for every product on Naar Shop against Amazon, Flipkart, Meesho and ${sellers?.count ?? 0} authorized seller websites — same prices you see on naar.io.`}
      />

      <div className="naar-card px-5 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex-1 min-w-[220px]">
          <label className="block text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm mb-2">
            Search
          </label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            type="search"
            placeholder="SKU or product name"
            className="w-full px-4 py-3 rounded-pill bg-white/70 border border-naar-pebble text-forest placeholder:text-naar-warm focus:outline-none focus:ring-2 focus:ring-turquoise/30"
          />
        </div>

        <div className="flex items-end gap-3 shrink-0">
          <button
            type="button"
            onClick={() => setOnlyMismatches((v) => !v)}
            aria-pressed={onlyMismatches}
            className={`px-5 py-3 rounded-pill border font-bold text-sm transition-all ${
              onlyMismatches ? "border-turquoise/40 bg-turquoise/10 text-forest" : "border-naar-pebble bg-white/70 text-forest hover:bg-white"
            }`}
          >
            {onlyMismatches ? "Showing mismatches" : "Only mismatches"}
          </button>
        </div>
      </div>

      {runScan.isSuccess && isMobile && (
        <div
          className={`naar-card px-4 py-3 text-sm border-turquoise/30 bg-turquoise/8 text-forest`}
        >
          {runScan.data?.message ||
            "Competitor scan started. Amazon/Flipkart/Meesho links appear within ~1 minute; live prices may take longer."}
        </div>
      )}

      {scanStatus.data?.phase === "running" && isMobile && (
        <div className="naar-card px-4 py-3 text-sm border-turquoise/30 bg-turquoise/8 text-forest">
          Scanning competitors… {scanStatus.data.scanned}/{scanStatus.data.total} products processed. Refresh to see new links.
        </div>
      )}

      {scanStatus.data?.phase === "failed" && isMobile && (
        <div className="naar-card px-4 py-3 text-sm border-naar-red/30 bg-naar-red/8 text-forest">
          Last scan failed: {scanStatus.data.error || "unknown error"}
        </div>
      )}

      {isMobile ? (
        <>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              onClick={() => runScan.mutate()}
              disabled={runScan.isPending}
              className="btn-naar-primary"
            >
              {runScan.isPending ? "Starting scan…" : "▶ Run competitor scan"}
            </button>
          </div>
          <PriceComparisonMatrix searchTerm={normalizedSearch} onlyMismatches={onlyMismatches} showHeader={false} />
        </>
      ) : (
        <NaarShopCompareTable searchTerm={normalizedSearch} onlyMismatches={onlyMismatches} />
      )}
    </main>
  );
}
