// All calls go through the Next rewrite proxy /poc-api/* -> verify_app /api/*.
const BASE = "/poc-api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
  });
  const text = await r.text();
  const body = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const msg = (body && (body.error as string)) || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return body as T;
}

export const api = {
  sellers: () => req<import("./types").SellersResponse>("/sellers"),
  propose: (seller: string, marketplace: string) =>
    req<import("./types").ProposeResponse>(
      `/propose?seller=${encodeURIComponent(seller)}&marketplace=${marketplace}`
    ),
  confirm: (b: { seller_id: string; marketplace: string; store_url?: string; seller_display?: string }) =>
    req<{ ok: true }>("/confirm", { method: "POST", body: JSON.stringify(b) }),
  reject: (b: { seller_id: string; marketplace: string }) =>
    req<{ ok: true }>("/reject", { method: "POST", body: JSON.stringify(b) }),

  runPreview: () => req<import("./types").RunPreview>("/run/preview"),
  run: () => req<{ started: boolean; total: number }>("/run", { method: "POST", body: "{}" }),
  runStatus: () => req<import("./types").JobStatus>("/run/status"),
  results: (q: { status?: string; seller?: string; order?: string; limit?: number; offset?: number }) => {
    const p = new URLSearchParams();
    if (q.status) p.set("status", q.status);
    if (q.seller) p.set("seller", q.seller);
    if (q.order) p.set("order", q.order);
    p.set("limit", String(q.limit ?? 50));
    p.set("offset", String(q.offset ?? 0));
    return req<import("./types").ResultsResponse>(`/results?${p.toString()}`);
  },
  exportCsvUrl: () => `${BASE}/results/export.csv`,

  autoconfirmPreview: () => req<import("./types").SweepPreview>("/autoconfirm/preview"),
  autoconfirm: () => req<{ started: boolean; total: number }>("/autoconfirm", { method: "POST", body: "{}" }),
  autoconfirmStatus: () => req<import("./types").JobStatus>("/autoconfirm/status"),
};

export const MARKETS: { key: "amazon_in" | "flipkart" | "meesho"; label: string }[] = [
  { key: "amazon_in", label: "Amazon" },
  { key: "flipkart", label: "Flipkart" },
  { key: "meesho", label: "Meesho" },
];
