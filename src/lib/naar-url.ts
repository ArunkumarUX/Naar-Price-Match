import { config } from "./config.js";

/** Naar product detail pages are app-only; web users should land on the shop browse page. */
export function naarWebShopUrl(productName?: string): string {
  const base = config.NAAR_SHOP_URL.replace(/\/$/, "");
  const query = productName?.trim();
  if (!query) return base;
  return `${base}?q=${encodeURIComponent(query)}`;
}

export function normalizeNaarProductUrl(url: string | null | undefined, productName?: string): string {
  const fallback = naarWebShopUrl(productName);
  if (!url?.trim()) return fallback;

  try {
    const parsed = new URL(url);
    if (/\/shop\/product\/[^/?#]+/i.test(parsed.pathname)) {
      return naarWebShopUrl(productName);
    }
    return url;
  } catch {
    return fallback;
  }
}
