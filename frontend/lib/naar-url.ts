const NAAR_SHOP_URL = "https://naar.io/shop";

/** Product detail URLs on naar.io are app-only; link to the web shop instead. */
export function naarWebShopUrl(productName?: string): string {
  const query = productName?.trim();
  if (!query) return NAAR_SHOP_URL;
  return `${NAAR_SHOP_URL}?q=${encodeURIComponent(query)}`;
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
