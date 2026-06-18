"use client";

import { PageHeader } from "@/components/PageHeader";
import { useSellers } from "@/lib/api";
import { categoryColors } from "@/lib/brand";

export default function SellersPage() {
  const { data, isLoading } = useSellers();
  const sellers = data?.sellers || [];

  const byCategory = sellers.reduce<Record<string, typeof sellers>>((acc, s) => {
    const cat = s.category || "Other";
    (acc[cat] = acc[cat] || []).push(s);
    return acc;
  }, {});

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-8 pb-12">
      <PageHeader
        eyebrow="Seller Registry"
        title="Authorized Seller Websites"
        description={`${data?.count ?? 0} seller stores loaded for cross-platform price monitoring.`}
      />

      {isLoading ? (
        <p className="text-naar-warm">Loading sellers…</p>
      ) : (
        Object.entries(byCategory).map(([category, items]) => (
          <section key={category}>
            <h2 className="font-bold text-xs uppercase tracking-[0.14em] text-naar-warm mb-3">
              {category} <span className="text-turquoise-dim">({items.length})</span>
            </h2>
            <div className="grid md:grid-cols-2 gap-3">
              {items.map((s) => (
                <a
                  key={s.id}
                  href={s.website}
                  target="_blank"
                  rel="noreferrer"
                  className="naar-card flex items-center justify-between gap-3 p-4 hover:border-turquoise/40 hover:shadow-turquoise-glow transition-all"
                >
                  <div className="min-w-0">
                    <p className="font-bold text-sm text-forest truncate">{s.store_name}</p>
                    <p className="text-[10px] text-naar-warm truncate mt-0.5">{s.business_name}</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2.5 py-1 rounded-pill shrink-0 ${categoryColors[category] || "bg-naar-mist text-naar-slate"}`}>
                    {category}
                  </span>
                </a>
              ))}
            </div>
          </section>
        ))
      )}
    </main>
  );
}
