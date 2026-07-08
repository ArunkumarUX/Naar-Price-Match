"use client";

import { AlertsCardList } from "@/components/AlertsCardList";
import { AlertsTable } from "@/components/AlertsTable";
import { PageHeader } from "@/components/PageHeader";
import type { Severity } from "@/lib/api";
import { useAlerts } from "@/lib/api";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

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

function toSeverity(s: string | null): Severity | undefined {
  if (!s) return undefined;
  const lower = s.toLowerCase();
  return SEVERITIES.includes(lower as Severity) ? (lower as Severity) : undefined;
}

export default function AlertsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isMobile = useMediaQuery("(max-width: 1023px)");

  const severity = useMemo(() => toSeverity(searchParams.get("severity")), [searchParams]);
  const resolved = useMemo(() => {
    const raw = searchParams.get("resolved");
    if (raw == null) return false; // default: unresolved
    return raw === "true";
  }, [searchParams]);

  const { data: alerts = [], isLoading } = useAlerts({ limit: 200, severity, resolved });

  const setFilter = (next: { severity?: Severity; resolved?: boolean }) => {
    const params = new URLSearchParams(searchParams.toString());

    const hasResolved = Object.prototype.hasOwnProperty.call(next, "resolved");
    const hasSeverity = Object.prototype.hasOwnProperty.call(next, "severity");

    if (hasResolved) {
      if (typeof next.resolved === "boolean") params.set("resolved", next.resolved ? "true" : "false");
      else params.delete("resolved");
    }

    if (hasSeverity) {
      if (next.severity) params.set("severity", next.severity);
      else params.delete("severity");
    }

    const qs = params.toString();
    router.push(`${pathname}${qs ? `?${qs}` : ""}`);
  };

  const chipClass = (active: boolean) =>
    `px-3 py-1.5 rounded-pill text-xs font-bold transition-all ${
      active
        ? "bg-turquoise/12 text-forest border border-turquoise/40"
        : "bg-white/70 text-naar-slate border border-naar-pebble hover:bg-white"
    }`;

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-6 pb-12">
      <PageHeader
        eyebrow="Alerts"
        title="All Price Alerts"
        description="Flagged discrepancies across marketplaces and seller websites."
      />

      <div className="naar-card px-5 py-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">Status</span>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setFilter({ resolved: false })} className={chipClass(!resolved)}>
                Unresolved
              </button>
              <button type="button" onClick={() => setFilter({ resolved: true })} className={chipClass(resolved)}>
                Resolved
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm">Severity</span>
            <button type="button" className={chipClass(!severity)} onClick={() => setFilter({ severity: undefined })}>
              All
            </button>
            {SEVERITIES.map((sev) => (
              <button key={sev} type="button" className={chipClass(severity === sev)} onClick={() => setFilter({ severity: sev })}>
                {sev}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isMobile ? <AlertsCardList alerts={alerts} loading={isLoading} /> : <div className="naar-card overflow-hidden">
        <AlertsTable alerts={alerts} loading={isLoading} />
      </div>
      }
    </main>
  );
}
