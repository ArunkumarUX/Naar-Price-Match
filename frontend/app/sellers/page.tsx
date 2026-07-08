"use client";

import { PageHeader } from "@/components/PageHeader";
import { useSellers } from "@/lib/api";
import { categoryColors } from "@/lib/brand";
import { useMemo, useState } from "react";

export default function SellersPage() {
  const { data, isLoading } = useSellers();
  const sellers = data?.sellers || [];

  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("All");

  const normalizedQuery = query.trim().toLowerCase();
  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const s of sellers) set.add(s.category || "Other");
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [sellers]);

  const filtered = useMemo(() => {
    return sellers.filter((s) => {
      const cat = s.category || "Other";
      if (category !== "All" && cat !== category) return false;

      if (!normalizedQuery) return true;
      const haystack = [s.store_name, s.business_name, s.category].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [sellers, category, normalizedQuery]);

  const byCategory = useMemo(() => {
    return filtered.reduce<Record<string, typeof sellers>>((acc, s) => {
      const cat = s.category || "Other";
      (acc[cat] = acc[cat] || []).push(s);
      return acc;
    }, {});
  }, [filtered]);

  return (
    <main className="p-6 max-w-screen-xl mx-auto space-y-8 pb-12">
      <PageHeader
        eyebrow="Seller Registry"
        title="Authorized Seller Websites"
        description={`${data?.count ?? 0} seller stores loaded for cross-platform price monitoring.`}
      />

      <div className="naar-card px-5 py-4 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex-1 min-w-[220px]">
            <label className="block text-[10px] font-bold uppercase tracking-[0.14em] text-naar-warm mb-2">
              Search
            </label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              type="search"
              placeholder="Store name or business"
              className="w-full px-4 py-3 rounded-pill bg-white/70 border border-naar-pebble text-forest placeholder:text-naar-warm focus:outline-none focus:ring-2 focus:ring-turquoise/30"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={`px-3 py-1.5 rounded-pill text-xs font-bold border transition-all ${
              category === "All" ? "bg-turquoise/12 border-turquoise/40 text-forest" : "bg-white/70 border-naar-pebble text-naar-slate hover:bg-white"
            }`}
            onClick={() => setCategory("All")}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              className={`px-3 py-1.5 rounded-pill text-xs font-bold border transition-all ${
                category === c ? `bg-turquoise/12 border-turquoise/40 text-forest` : `bg-white/70 border-naar-pebble text-naar-slate hover:bg-white`
              }`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="text-naar-warm">Loading sellers…</p>
      ) : (
        filtered.length ? (
          Object.entries(byCategory).map(([cat, items]) => (
            <section key={cat}>
              <h2 className="font-bold text-xs uppercase tracking-[0.14em] text-naar-warm mb-3">
                {cat} <span className="text-turquoise-dim">({items.length})</span>
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
                    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-pill shrink-0 ${categoryColors[cat] || "bg-naar-mist text-naar-slate"}`}>
                      {cat}
                    </span>
                  </a>
                ))}
              </div>
            </section>
          ))
        ) : (
          <div className="naar-card p-6 text-naar-warm space-y-2">
            <p>No sellers match your filters.</p>
            <p className="text-sm">
              Tip: if the registry looks incomplete, run <strong>Run Full Scan</strong> on the dashboard to refresh matching and links.
            </p>
          </div>
        )
      )}
    </main>
  );
}
