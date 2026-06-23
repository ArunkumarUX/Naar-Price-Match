import { config } from "../lib/config.js";
import { normalizeNaarProductUrl, naarWebShopUrl } from "../lib/naar-url.js";
import type { NaarProduct } from "./naar.scraper.js";

type UnknownRecord = Record<string, unknown>;

export function extractCatalogItems(payload: unknown): UnknownRecord[] {
  if (Array.isArray(payload)) {
    return payload.filter((item): item is UnknownRecord => typeof item === "object" && item !== null);
  }
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const record = payload as UnknownRecord;
  for (const key of ["products", "data", "items", "results", "content"]) {
    const value = record[key];
    if (Array.isArray(value)) {
      return value.filter((item): item is UnknownRecord => typeof item === "object" && item !== null);
    }
  }
  return [];
}

function variantLabel(variant: UnknownRecord): string {
  const name = String(variant.variantName ?? "").trim();
  const value = variant.variantValue;
  const option = String(variant.variantOption ?? "").trim();

  if (name && value != null && option) {
    return `${name} ${value}${option}`;
  }
  if (name && value != null) {
    return `${name} ${value}`;
  }
  if (name) return name;
  return String(variant.variantName ?? variant.variantType ?? "default");
}

function categoryLabel(item: UnknownRecord): string | undefined {
  const category = item.category as UnknownRecord | undefined;
  const subCategory = item.subCategory as UnknownRecord | undefined;
  const parts = [category?.title, subCategory?.title].map((v) => String(v ?? "").trim()).filter(Boolean);
  return parts.length ? parts.join(" / ") : undefined;
}

function productUrl(_productId: string, title: string): string {
  return naarWebShopUrl(title);
}

function resolveProductUrl(item: UnknownRecord, productId: string, title: string): string {
  const raw = String(item.url ?? item.productUrl ?? "").trim();
  if (raw) return normalizeNaarProductUrl(raw, title);
  return productId ? productUrl(productId, title) : config.NAAR_SHOP_URL;
}

function parsePrice(value: unknown): number | null {
  if (value == null) return null;
  const n = parseFloat(String(value).replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : null;
}

function isActiveProduct(item: UnknownRecord): boolean {
  const status = String(item.status ?? "active").toLowerCase();
  return status === "active";
}

/** Parse Naar commerce API documents (title + variants[]). */
export function parseNaarCommerceCatalog(payload: unknown): NaarProduct[] {
  const items = extractCatalogItems(payload);
  const rows: NaarProduct[] = [];

  for (const item of items) {
    if (!isActiveProduct(item)) continue;

    const productId = String(item._id ?? item.id ?? "").trim();
    const title = String(item.title ?? item.name ?? item.productName ?? "").trim();
    if (!title) continue;

    const variants = Array.isArray(item.variants) ? (item.variants as UnknownRecord[]) : [];
    const category = categoryLabel(item);
    const seller = item.seller as UnknownRecord | undefined;
    const storeName = seller?.storeName ? String(seller.storeName) : undefined;

    if (variants.length === 0) {
      const price = parsePrice(item.price ?? item.sellingPrice ?? item.mrp);
      if (!price) continue;
      rows.push({
        sku: String(item.sku ?? (productId || title.slice(0, 40))),
        name: title,
        variant: "default",
        price,
        url: resolveProductUrl(item, productId, title),
        category,
        source: storeName ? `naar_api:${storeName}` : "naar_api",
      });
      continue;
    }

    for (const variant of variants) {
      const price = parsePrice(
        variant.price ?? variant.originalPriceWithTax ?? variant.priceWithoutTax ?? item.price,
      );
      if (!price) continue;

      const variantId = String(variant._id ?? variant.variantId ?? "").trim();
      const sku =
        variantId && productId
          ? `${productId}:${variantId}`
          : String(variant.sku ?? (productId || title.slice(0, 40)));

      rows.push({
        sku,
        name: title,
        variant: variantLabel(variant),
        price,
        url: resolveProductUrl(item, productId, title),
        category,
        source: storeName ? `naar_api:${storeName}` : "naar_api",
      });
    }
  }

  return dedupeProducts(rows);
}

function dedupeProducts(products: NaarProduct[]): NaarProduct[] {
  const seen = new Set<string>();
  const out: NaarProduct[] = [];
  for (const product of products) {
    const key = product.sku || `${product.name}:${product.variant}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(product);
  }
  return out;
}
