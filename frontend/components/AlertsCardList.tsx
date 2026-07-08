"use client";

import { useResolveAlert, type Alert, type Severity } from "@/lib/api";
import { brand } from "@/lib/brand";
import { SeverityBadge } from "@/components/SeverityBadge";

function formatInr(n: number | null | undefined) {
  if (n == null || n <= 0) return "—";
  return `₹${n.toLocaleString("en-IN")}`;
}

function deviationColor(v: number | null | undefined) {
  if (v == null) return brand.warm;
  return v > 0 ? brand.redOrange : brand.green;
}

function ResolveButton({ id }: { id: number }) {
  const resolve = useResolveAlert();
  return (
    <button
      className="text-turquoise-dim hover:underline text-xs font-bold disabled:opacity-50"
      disabled={resolve.isPending}
      onClick={() => resolve.mutate(id)}
      type="button"
    >
      {resolve.isPending ? "Resolving…" : "Resolve"}
    </button>
  );
}

export function AlertsCardList({ alerts, loading }: { alerts: Alert[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="p-8 text-center text-naar-warm">
        Loading alerts…
      </div>
    );
  }

  if (!alerts.length) {
    return (
      <div className="naar-card p-8 text-center text-naar-warm space-y-2">
        <p>No alerts for the selected filters.</p>
        <p className="text-sm">Run a scan from the dashboard to populate new discrepancies.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {alerts.map((a) => {
        const delta = a.deviation_pct;
        return (
          <div key={a.id} className="naar-card p-5 space-y-3 hover:border-turquoise/30 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={a.severity as Severity} />
                  <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">
                    {a.platform || "seller"}
                  </span>
                </div>
                <p className="font-extrabold text-forest mt-2 truncate">
                  SKU {a.product_id}
                </p>
                <p className="text-sm text-naar-slate mt-1 break-words">
                  {a.details}
                </p>
              </div>

              <ResolveButton id={a.id} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-4 bg-sandstone/50 rounded-naar border border-naar-mist/60">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">Naar</p>
                <p className="text-xl font-extrabold text-forest tabular-nums mt-1">{formatInr(a.naar_price)}</p>
              </div>
              <div className="p-4 bg-white rounded-naar border border-naar-mist/60">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">Competitor</p>
                <p className="text-xl font-extrabold text-forest tabular-nums mt-1">{formatInr(a.competitor_price)}</p>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">Deviation</p>
                <p className="text-sm font-bold mt-1" style={{ color: deviationColor(delta) }}>
                  {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`}
                </p>
              </div>
              <p className="text-[10px] text-naar-warm">
                Created {new Date(a.created_at).toLocaleString()}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

