import { config } from "../lib/config.js";
import { parseNaarCommerceCatalog } from "./naar-catalog.parser.js";
import type { NaarProduct } from "./naar.scraper.js";

export interface CatalogFetchResult {
  products: NaarProduct[];
  source: string;
}

function catalogHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    Origin: config.NAAR_BASE_URL,
    Referer: config.NAAR_SHOP_URL,
  };
  if (config.NAAR_CATALOG_API_KEY) {
    headers.Authorization = `Bearer ${config.NAAR_CATALOG_API_KEY}`;
  }
  return headers;
}

export function catalogApiCandidates(): string[] {
  const configured = config.NAAR_CATALOG_API.trim();
  const defaults = [
    `${config.NAAR_BASE_URL}/api/v1/ecommerce/products`,
    `${config.NAAR_BASE_URL}/api/ecommerce/products`,
    `${config.NAAR_BASE_URL}/api/shop/products`,
    `${config.NAAR_BASE_URL}/api/products`,
    `${config.NAAR_BASE_URL}/api/v1/products`,
    "https://api.naar.io/ecommerce/products",
    "https://api.naar.io/v1/products",
    "https://api.naar.io/products",
    "https://api.naar.io/shop/products",
    `${config.NAAR_BASE_URL}/products.json`,
  ];
  return [...new Set([configured, ...defaults].filter(Boolean))];
}

async function fetchCatalogFromUrl(url: string): Promise<CatalogFetchResult | null> {
  const res = await fetch(url, { headers: catalogHeaders() });
  if (!res.ok) return null;

  const data = await res.json();
  const products = parseNaarCommerceCatalog(data);
  if (!products.length) return null;

  return { products, source: url };
}

/** Fetch Naar catalog from configured API or known commerce endpoints. */
export async function fetchNaarCommerceCatalog(): Promise<CatalogFetchResult | null> {
  for (const url of catalogApiCandidates()) {
    try {
      const result = await fetchCatalogFromUrl(url);
      if (result) return result;
    } catch {
      /* try next candidate */
    }
  }
  return null;
}
