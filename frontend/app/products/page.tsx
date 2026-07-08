"use client";

import { PageHeader } from "@/components/PageHeader";
import { useProducts } from "@/lib/api";
import { normalizeNaarProductUrl } from "@/lib/naar-url";
import { useMemo, useState } from "react";

export default function ProductsPage() {
  const { data: products = [], isLoading } = useProducts();
  const [query, setQuery] = useState("");

  const normalizedQuery = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!normalizedQuery) return products;
    return products.filter((p) => {
      const haystack = [p.sku, p.name, p.variant, p.category].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [products, normalizedQuery]);

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-6 pb-12">
      <PageHeader
        eyebrow="Catalog"
        title="Naar Product Catalog"
        description="Products tracked for weekly price parity across all channels."
      />

      <div className="naar-card px-5 py-4">
        <label className="block text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm mb-2">
          Search
        </label>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          type="search"
          placeholder="SKU or product name"
          className="w-full px-4 py-3 rounded-pill bg-white/70 border border-naar-pebble text-forest placeholder:text-naar-warm focus:outline-none focus:ring-2 focus:ring-turquoise/30"
        />
        <p className="text-xs text-naar-warm mt-3">
          {filtered.length} result{filtered.length === 1 ? "" : "s"}
        </p>
      </div>

      <div className="grid gap-3">
        {isLoading && <p className="text-naar-warm">Loading…</p>}
        {filtered.map((p) => (
          <div key={p.id} className="naar-card p-5 flex justify-between items-center gap-4 hover:border-turquoise/30 transition-colors">
            <div>
              <p className="text-[10px] font-bold text-naar-warm uppercase tracking-wide">{p.sku}</p>
              <p className="font-extrabold text-forest mt-0.5">{p.name}</p>
              <p className="text-sm text-naar-slate">{p.variant} · {p.category}</p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-xl font-extrabold text-forest tabular-nums">₹{p.base_price.toLocaleString("en-IN")}</p>
              <a
                href={normalizeNaarProductUrl(p.url, p.name)}
                target="_blank"
                rel="noreferrer"
                title="Product detail pages are in the Naar app. This opens the web shop."
                className="text-xs text-turquoise-dim font-bold hover:underline"
              >
                Browse Naar Shop →
              </a>
            </div>
          </div>
        ))}
        {!isLoading && !products.length && (
          <p className="text-naar-warm text-center py-12">
            No products yet. Run a full scan from the dashboard to populate the catalog.
          </p>
        )}
        {!isLoading && products.length > 0 && !filtered.length && (
          <p className="text-naar-warm text-center py-12">
            No products match your search. Try a different SKU or clear the filter.
          </p>
        )}
      </div>
    </main>
  );
}
