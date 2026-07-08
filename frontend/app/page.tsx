"use client";

import { AlertsTable } from "@/components/AlertsTable";
import { ProductionModeBanner } from "@/components/ProductionModeBanner";
import { TrendChart } from "@/components/TrendChart";
import {
  useAlertSummary,
  useAlerts,
  useComparisonMatrix,
  useRunScan,
  useSyncCatalog,
  type Severity,
} from "@/lib/api";
import { parityStatus, severityColors } from "@/lib/brand";
import Link from "next/link";

const SEVERITY_META: Record<
  Severity,
  { label: string; hint: string; accent: string }
> = {
  critical: { label: "Critical", hint: "Needs immediate action", accent: "bg-naar-red" },
  high: { label: "High", hint: "Review today", accent: "bg-naar-pumpkin" },
  medium: { label: "Medium", hint: "Monitor closely", accent: "bg-naar-honey" },
  low: { label: "Low", hint: "Within tolerance", accent: "bg-naar-green" },
};

export default function Dashboard() {
  const { data: alerts = [], isLoading } = useAlerts({ limit: 8, resolved: false });
  const { data: summary = {} } = useAlertSummary();
  const { data: comparison } = useComparisonMatrix();
  const runScan = useRunScan();
  const syncCatalog = useSyncCatalog();

  const chartData = (["critical", "high", "medium", "low"] as Severity[]).map((sev) => ({
    sev,
    count: summary[sev] ?? 0,
  }));

  const totalOpen = chartData.reduce((sum, d) => sum + d.count, 0);
  const products = comparison?.products || [];
  const mismatchCount = products.filter((p) => p.summary?.has_discrepancy).length;
  const topMismatches = products
    .filter((p) => p.summary?.has_discrepancy)
    .slice(0, 4);

  return (
    <main className="pb-16">
      {/* Hero */}
      <section className="border-b border-naar-mist bg-gradient-to-br from-forest via-[#052222] to-[#063636] text-cloud">
        <div className="max-w-screen-xl mx-auto px-6 py-10 md:py-12">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 text-[0.7rem] font-bold uppercase tracking-[0.18em] text-turquoise mb-3">
                <span className="w-[18px] h-0.5 bg-turquoise shrink-0" />
                naar.io/shop · Command Center
              </div>
              <h1 className="text-3xl md:text-4xl font-extrabold leading-tight tracking-tight">
                Price Parity Overview
              </h1>
              <p className="text-cloud/60 mt-3 leading-relaxed text-sm md:text-base">
                Spot violations, sync the catalog, and jump straight into the alerts that matter.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => syncCatalog.mutate()}
                disabled={syncCatalog.isPending || runScan.isPending}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-white/10 text-cloud font-bold text-sm border border-white/15 hover:bg-white/15 transition-all disabled:opacity-60"
              >
                {syncCatalog.isPending ? "Fetching catalog…" : "↻ Sync Catalog"}
              </button>
              <button
                onClick={() => runScan.mutate()}
                disabled={runScan.isPending || syncCatalog.isPending}
                className="btn-naar-primary"
              >
                {runScan.isPending ? "Scanning…" : "▶ Run Full Scan"}
              </button>
            </div>
          </div>

          <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-naar bg-white/6 border border-white/10 px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-cloud/40">Open alerts</p>
              <p className="text-3xl font-extrabold tabular-nums mt-1 text-turquoise">{totalOpen}</p>
            </div>
            <div className="rounded-naar bg-white/6 border border-white/10 px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-cloud/40">Products tracked</p>
              <p className="text-3xl font-extrabold tabular-nums mt-1">{products.length}</p>
            </div>
            <div className="rounded-naar bg-white/6 border border-white/10 px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-cloud/40">Mismatches</p>
              <p className="text-3xl font-extrabold tabular-nums mt-1 text-naar-honey">{mismatchCount}</p>
            </div>
            <div className="rounded-naar bg-white/6 border border-white/10 px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-cloud/40">Critical</p>
              <p className="text-3xl font-extrabold tabular-nums mt-1 text-naar-red">{summary.critical ?? 0}</p>
            </div>
          </div>
        </div>
      </section>

      <div className="max-w-screen-xl mx-auto px-6 space-y-8 -mt-4 pt-8">
        <ProductionModeBanner />

        {(syncCatalog.isSuccess || runScan.isSuccess) && (
          <div className="space-y-3">
            {syncCatalog.isSuccess && (
              <div
                className={`naar-card px-4 py-3 text-sm ${
                  syncCatalog.data?.status === "ok"
                    ? "border-naar-green/30 bg-naar-green/8 text-forest"
                    : "border-naar-honey/30 bg-naar-honey/10 text-forest"
                }`}
              >
                {syncCatalog.data?.status === "ok"
                  ? `Catalog synced — ${syncCatalog.data?.imported ?? 0} products from Naar shop`
                  : syncCatalog.data?.message || "Catalog sync failed"}
              </div>
            )}
            {runScan.isSuccess && (
              <div
                className={`naar-card px-4 py-3 text-sm ${
                  runScan.data?.catalog_error
                    ? "border-naar-honey/30 bg-naar-honey/10 text-forest"
                    : "border-naar-green/30 bg-naar-green/8 text-forest"
                }`}
              >
                {runScan.data?.catalog_error
                  ? runScan.data.catalog_error
                  : runScan.data?.message ||
                    (runScan.data?.status === "started"
                      ? `Competitor scan started for up to ${runScan.data?.limit ?? 10} products — refresh compare in a few minutes.`
                      : `Scan complete — ${runScan.data?.scanned ?? 0} products checked`)}
              </div>
            )}
          </div>
        )}

        {/* Severity KPIs */}
        <section>
          <div className="flex items-end justify-between gap-3 mb-4">
            <div>
              <div className="naar-eyebrow">Severity Radar</div>
              <h2 className="text-xl font-extrabold text-forest">Open alerts by priority</h2>
            </div>
            <Link href="/alerts?resolved=false" className="text-sm font-bold text-turquoise-dim hover:underline">
              View all alerts →
            </Link>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {(["critical", "high", "medium", "low"] as Severity[]).map((sev) => {
              const meta = SEVERITY_META[sev];
              return (
                <Link key={sev} href={`/alerts?severity=${sev}&resolved=false`} className="group block">
                  <div className="naar-card overflow-hidden transition-all group-hover:border-turquoise/40 group-hover:shadow-turquoise-glow group-hover:-translate-y-0.5">
                    <div className={`h-1.5 ${meta.accent}`} />
                    <div className="p-5">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-bold text-forest">{meta.label}</p>
                        <span className="text-[10px] font-bold uppercase tracking-wide text-naar-warm opacity-0 group-hover:opacity-100 transition-opacity">
                          Open →
                        </span>
                      </div>
                      <p
                        className="text-4xl font-extrabold mt-2 tabular-nums tracking-tight"
                        style={{ color: severityColors[sev] }}
                      >
                        {summary[sev] ?? 0}
                      </p>
                      <p className="text-xs text-naar-warm mt-2">{meta.hint}</p>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>

        {/* Chart + Top mismatches */}
        <section className="grid lg:grid-cols-5 gap-5" aria-labelledby="insights-heading">
          <h2 id="insights-heading" className="sr-only">
            Alert insights and top mismatches
          </h2>

          <article
            className="lg:col-span-3 naar-card-dark p-6 relative overflow-hidden"
            aria-labelledby="alert-volume-heading"
          >
            <div
              className="pointer-events-none absolute -top-16 -right-10 w-56 h-56 rounded-full bg-turquoise/10 blur-3xl"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -bottom-20 -left-10 w-48 h-48 rounded-full bg-naar-violet/10 blur-3xl"
              aria-hidden
            />

            <div className="relative flex flex-wrap items-start justify-between gap-4 mb-5">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-turquoise/80 mb-1.5">
                  Severity mix
                </p>
                <h3 id="alert-volume-heading" className="text-lg font-extrabold text-cloud tracking-tight">
                  Alert volume
                </h3>
                <p className="text-sm text-cloud/50 mt-1">
                  {totalOpen === 0
                    ? "No unresolved alerts right now."
                    : `${totalOpen} open alert${totalOpen === 1 ? "" : "s"} across severity levels.`}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <span
                  className="inline-flex items-center gap-2 rounded-pill px-3 py-1.5 text-xs font-bold bg-white/8 border border-white/10 text-cloud"
                  aria-label={`${totalOpen} open alerts`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-turquoise" aria-hidden />
                  {totalOpen} open
                </span>
                <Link
                  href="/alerts?resolved=false"
                  className="text-xs font-bold text-turquoise hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-turquoise rounded-sm"
                >
                  Open queue →
                </Link>
              </div>
            </div>

            <div className="relative">
              <TrendChart data={chartData} dark />
            </div>
          </article>

          <article
            className="lg:col-span-2 naar-card overflow-hidden flex flex-col"
            aria-labelledby="top-mismatches-heading"
          >
            <div className="px-5 py-4 border-b border-naar-mist bg-sandstone/60 flex items-center justify-between gap-3">
              <div>
                <h3 id="top-mismatches-heading" className="font-bold text-forest">
                  Top mismatches
                </h3>
                <p className="text-xs text-naar-warm mt-0.5">{mismatchCount} products off parity</p>
              </div>
              <Link
                href="/compare"
                className="text-xs font-bold text-turquoise-dim hover:underline shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-turquoise rounded-sm"
              >
                Full compare →
              </Link>
            </div>

            <div className="divide-y divide-naar-mist flex-1">
              {topMismatches.length ? (
                topMismatches.map((p) => {
                  const lowest = p.summary?.lowest_competitor;
                  const status = lowest?.status || "missing";
                  const style = parityStatus[status as keyof typeof parityStatus] || parityStatus.missing;
                  return (
                    <div key={p.sku} className="px-5 py-4 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-naar-warm">{p.sku}</p>
                        <p className="font-bold text-sm text-forest truncate mt-0.5">{p.name}</p>
                        <p className="text-xs text-naar-slate mt-1">
                          Naar ₹{p.naar_price.toLocaleString("en-IN")}
                          {lowest?.price != null && (
                            <>
                              {" "}
                              · Lowest ₹{lowest.price.toLocaleString("en-IN")}
                              {lowest.source ? ` (${lowest.source})` : ""}
                            </>
                          )}
                        </p>
                      </div>
                      <span className={`shrink-0 text-[10px] font-bold px-2.5 py-1 rounded-pill ${style.bg} ${style.text}`}>
                        {lowest?.label || style.label}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="px-5 py-12 text-center text-naar-warm text-sm">
                  {products.length
                    ? "All scanned products look on parity."
                    : "No comparison data yet — run a full scan."}
                </div>
              )}
            </div>
          </article>
        </section>

        {/* Active alerts */}
        <section className="naar-card overflow-hidden">
          <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4 bg-sandstone/70 border-b border-naar-mist">
            <div>
              <h2 className="font-bold text-forest">Latest open alerts</h2>
              <p className="text-xs text-naar-warm mt-0.5">Showing up to 8 unresolved issues</p>
            </div>
            <div className="flex items-center gap-4">
              <a
                href="/backend-api/alerts/export/csv"
                className="text-sm text-turquoise-dim font-bold hover:underline"
              >
                Export CSV
              </a>
              <Link href="/alerts?resolved=false" className="text-sm text-turquoise-dim font-bold hover:underline">
                See all →
              </Link>
            </div>
          </div>
          <AlertsTable alerts={alerts} loading={isLoading} />
        </section>
      </div>
    </main>
  );
}
