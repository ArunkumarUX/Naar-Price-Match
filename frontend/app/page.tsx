"use client";

import { AlertsTable } from "@/components/AlertsTable";
import { ProductionModeBanner } from "@/components/ProductionModeBanner";
import { PageHeader } from "@/components/PageHeader";
import { PriceComparisonMatrix } from "@/components/PriceComparisonMatrix";
import { TrendChart } from "@/components/TrendChart";
import { useAlertSummary, useAlerts, useRunScan, useSyncCatalog, type Severity } from "@/lib/api";
import { severityColors } from "@/lib/brand";

export default function Dashboard() {
  const { data: alerts = [], isLoading } = useAlerts({ limit: 100 });
  const { data: summary = {} } = useAlertSummary();
  const runScan = useRunScan();
  const syncCatalog = useSyncCatalog();

  const chartData = (["critical", "high", "medium", "low"] as Severity[]).map((sev) => ({
    sev,
    count: summary[sev] ?? 0,
  }));

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-8 pb-12">
      <PageHeader
        eyebrow="naar.io/shop · Weekly Cron"
        title="Price Parity Command Center"
        description="Monitor exact Naar Shop prices against Amazon, Flipkart, Meesho and authorized seller websites."
        action={
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => syncCatalog.mutate()}
              disabled={syncCatalog.isPending || runScan.isPending}
              className="btn-naar-secondary"
            >
              {syncCatalog.isPending ? "Fetching catalog…" : "↻ Sync Naar Catalog"}
            </button>
            <button onClick={() => runScan.mutate()} disabled={runScan.isPending || syncCatalog.isPending} className="btn-naar-primary">
              {runScan.isPending ? "Scanning…" : "▶ Run Full Scan"}
            </button>
          </div>
        }
      />

      <ProductionModeBanner />

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
            : `Scan complete — ${runScan.data?.alerts ?? 0} alerts across ${runScan.data?.products ?? 0} products`}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {(["critical", "high", "medium", "low"] as Severity[]).map((sev) => (
          <div key={sev} className="naar-card p-5">
            <p className="text-sm text-naar-warm capitalize font-semibold">{sev}</p>
            <p className="text-4xl font-extrabold mt-1 tabular-nums" style={{ color: severityColors[sev] }}>
              {summary[sev] ?? 0}
            </p>
          </div>
        ))}
      </div>

      <div className="naar-card-dark p-6">
        <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-cloud/45 mb-4">Open Alerts by Severity</h2>
        <TrendChart data={chartData} dark />
      </div>

      <PriceComparisonMatrix />

      <div className="naar-card overflow-hidden">
        <div className="flex justify-between items-center px-5 py-4 bg-sandstone/80 border-b border-naar-mist">
          <h2 className="font-bold text-forest">Active Alerts ({alerts.length})</h2>
          <a href="/backend-api/alerts/export/csv" className="text-sm text-turquoise-dim font-bold hover:underline">
            Export CSV
          </a>
        </div>
        <AlertsTable alerts={alerts} loading={isLoading} />
      </div>
    </main>
  );
}
