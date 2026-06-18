"use client";

import { PageHeader } from "@/components/PageHeader";
import { useProducts } from "@/lib/api";

export default function ProductsPage() {
  const { data: products = [], isLoading } = useProducts();

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-6 pb-12">
      <PageHeader
        eyebrow="Catalog"
        title="Naar Product Catalog"
        description="Products tracked for weekly price parity across all channels."
      />
      <div className="grid gap-3">
        {isLoading && <p className="text-naar-warm">Loading…</p>}
        {products.map((p) => (
          <div key={p.id} className="naar-card p-5 flex justify-between items-center gap-4 hover:border-turquoise/30 transition-colors">
            <div>
              <p className="text-[10px] font-bold text-naar-warm uppercase tracking-wide">{p.sku}</p>
              <p className="font-extrabold text-forest mt-0.5">{p.name}</p>
              <p className="text-sm text-naar-slate">{p.variant} · {p.category}</p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-xl font-extrabold text-forest tabular-nums">₹{p.base_price.toLocaleString("en-IN")}</p>
              <a href={p.url} target="_blank" rel="noreferrer" className="text-xs text-turquoise-dim font-bold hover:underline">
                View on Naar →
              </a>
            </div>
          </div>
        ))}
        {!isLoading && !products.length && (
          <p className="text-naar-warm text-center py-12">No products yet — run a scan from the dashboard</p>
        )}
      </div>
    </main>
  );
}
