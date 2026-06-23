import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

/** Browser uses same-origin runtime proxy; SSR uses direct backend URL. */
export const API_BASE = typeof window !== "undefined" ? "/backend-api" : getServerApiBase();

function getServerApiBase(): string {
  return (
    process.env.BACKEND_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    (process.env.NODE_ENV === "production" ? "https://naar-api.onrender.com" : "http://127.0.0.1:8000")
  ).replace(/\/$/, "");
}

const BASE = API_BASE;

export type Severity = "critical" | "high" | "medium" | "low";

export interface Alert {
  id: number;
  product_id: string;
  alert_type: string;
  severity: Severity;
  naar_price: number;
  competitor_price: number | null;
  deviation_pct: number | null;
  platform: string | null;
  details: string;
  is_resolved: boolean;
  created_at: string;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  variant: string | null;
  base_price: number;
  category: string | null;
  url: string;
}

export interface ChannelPrice {
  platform?: string;
  price: number | null;
  url?: string | null;
  status: string;
  deviation_pct?: number | null;
  label?: string;
  match_confidence?: number | null;
  seller_name?: string;
  seller_id?: string;
  seller_website?: string;
  seller_category?: string;
  title?: string;
}

export interface ComparisonProduct {
  sku: string;
  name: string;
  variant?: string | null;
  naar_price: number;
  naar_url?: string;
  channels: {
    amazon?: ChannelPrice;
    flipkart?: ChannelPrice;
    meesho?: ChannelPrice;
    sellers?: ChannelPrice[];
  };
  summary?: {
    lowest_competitor?: ChannelPrice & { source?: string };
    seller_count_matched?: number;
    best_seller?: ChannelPrice;
    has_discrepancy?: boolean;
  };
}

export interface Seller {
  id: string;
  store_name: string;
  business_name: string;
  website: string;
  category: string;
  active: boolean;
}

export const useAlerts = (params?: { severity?: Severity; limit?: number }) =>
  useQuery<Alert[]>({
    queryKey: ["alerts", params],
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (params?.severity) qs.set("severity", params.severity);
      if (params?.limit) qs.set("limit", String(params.limit));
      const res = await fetch(`${BASE}/alerts/?${qs}`);
      if (!res.ok) throw new Error("Failed to fetch alerts");
      return res.json();
    },
    refetchInterval: 60_000,
  });

export const useAlertSummary = () =>
  useQuery<Record<string, number>>({
    queryKey: ["alert-summary"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/alerts/summary`);
      if (!res.ok) return {};
      return res.json();
    },
    refetchInterval: 60_000,
  });

export const useProducts = () =>
  useQuery<Product[]>({
    queryKey: ["products"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/products/?limit=100`);
      if (!res.ok) throw new Error("Failed to fetch products");
      return res.json();
    },
    refetchInterval: 60_000,
  });

export const useResolveAlert = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      fetch(`${BASE}/alerts/${id}/resolve`, { method: "POST" }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-summary"] });
    },
  });
};

export const useRunScan = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => fetch(`${BASE}/reports/run-scan`, { method: "POST" }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-summary"] });
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
};

export const useSyncCatalog = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => fetch(`${BASE}/reports/sync-catalog`, { method: "POST" }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
};

export const useComparisonMatrix = () =>
  useQuery<{ products: ComparisonProduct[]; seller_registry_count: number }>({
    queryKey: ["comparison"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/comparison/matrix`, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(body || `API error ${res.status}`);
      }
      return res.json();
    },
    refetchInterval: 60_000,
    retry: 2,
  });

export const useSellers = () =>
  useQuery<{ count: number; sellers: Seller[] }>({
    queryKey: ["sellers"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/comparison/sellers`);
      if (!res.ok) throw new Error("Failed to fetch sellers");
      return res.json();
    },
  });

export interface HealthStatus {
  status: string;
  demo_mode: boolean;
  production_mode: boolean;
  claude_enabled: boolean;
  claude_model: string | null;
}

export const useHealth = () =>
  useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/health`);
      if (!res.ok) throw new Error("API unavailable");
      return res.json();
    },
    refetchInterval: 30_000,
  });
