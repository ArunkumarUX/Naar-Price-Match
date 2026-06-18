"use client";

import { AlertsTable } from "@/components/AlertsTable";
import { PageHeader } from "@/components/PageHeader";
import { useAlerts } from "@/lib/api";

export default function AlertsPage() {
  const { data: alerts = [], isLoading } = useAlerts({ limit: 200 });

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-6 pb-12">
      <PageHeader
        eyebrow="Alerts"
        title="All Price Alerts"
        description="Flagged discrepancies across marketplaces and seller websites."
      />
      <div className="naar-card overflow-hidden">
        <AlertsTable alerts={alerts} loading={isLoading} />
      </div>
    </main>
  );
}
