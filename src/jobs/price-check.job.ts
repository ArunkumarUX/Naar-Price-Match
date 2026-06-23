import { buildComparisonRow } from "../engine/price.comparator.js";
import { matchProduct, toMatchedListing } from "../matcher/product.matcher.js";
import { searchAmazon, searchFlipkart, searchMeesho } from "../scrapers/marketplace.scraper.js";
import { searchSellers } from "../scrapers/seller.registry.js";
import { config } from "../lib/config.js";
import { prisma } from "../lib/prisma.js";
import { syncNaarCatalog } from "../services/catalog.js";
import type { MatchCandidate } from "../matcher/product.matcher.js";

export async function runFullPriceCheck(limit = 25) {
  let dbProducts = await prisma.product.findMany({
    where: { isActive: true },
    take: limit,
    orderBy: { updatedAt: "desc" },
  });

  if (!dbProducts.length) {
    const catalog = await syncNaarCatalog();
    if (!catalog.imported) {
      return {
        scanned: 0,
        skus: [] as string[],
        catalog_error:
          "Naar catalog empty — set NAAR_CATALOG_API on Render or run POST /reports/sync-catalog first.",
      };
    }
    dbProducts = await prisma.product.findMany({
      where: { isActive: true },
      take: limit,
      orderBy: { updatedAt: "desc" },
    });
  }

  const scanned: string[] = [];
  let count = 0;

  for (const product of dbProducts) {
    const naarProduct = {
      sku: product.sku,
      name: product.name,
      variant: product.variant ?? "default",
      price: product.basePrice,
      url: product.url,
      category: product.category ?? undefined,
    };

    const matches: Record<string, unknown> = {};
    for (const [platform, search] of [
      ["amazon", searchAmazon],
      ["flipkart", searchFlipkart],
      ["meesho", searchMeesho],
    ] as const) {
      const candidates = await search(product.name, 3);
      const matched = await matchProduct(naarProduct, candidates as MatchCandidate[], config.MIN_MATCH_CONFIDENCE);
      matches[platform] = matched[0] ? toMatchedListing(matched[0]) : null;
    }

    const sellerCandidates = await searchSellers(product.name, 8);
    const sellerMatched = await matchProduct(
      naarProduct,
      sellerCandidates as MatchCandidate[],
      config.MIN_MATCH_CONFIDENCE - 0.1,
    );
    matches.sellers = sellerMatched.slice(0, 5).map(toMatchedListing);

    const row = buildComparisonRow(naarProduct, matches);
    await persistComparisonRow(product.sku, row);
    scanned.push(product.sku);
    count++;
    if (count >= limit) break;
  }

  return { scanned: count, skus: scanned };
}

async function persistComparisonRow(sku: string, row: Record<string, unknown>) {
  const product = await prisma.product.findUnique({ where: { sku } });
  if (!product) return;

  const channels = row.channels as Record<string, unknown>;
  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const ch = channels[platform] as Record<string, unknown> | undefined;
    if (!ch?.price) continue;
    await saveListingSnapshot(product.id, platform, ch);
  }

  const sellers = (channels.sellers as Record<string, unknown>[]) ?? [];
  for (const s of sellers) {
    if (!s.price) continue;
    await saveListingSnapshot(product.id, "seller", s, String(s.seller_name ?? ""));
  }
}

async function saveListingSnapshot(
  productId: string,
  platform: "amazon" | "flipkart" | "meesho" | "seller",
  ch: Record<string, unknown>,
  sellerName?: string,
) {
  const listing = await prisma.productListing.create({
    data: {
      productId,
      platform,
      platformId: String(ch.platformId ?? ch.seller_id ?? platform),
      sellerName: sellerName || null,
      platformUrl: String(ch.url ?? ""),
      matchConfidence: Number(ch.match_confidence ?? 0),
      matchMethod: String(ch.match_method ?? "unknown"),
    },
  });

  await prisma.priceSnapshot.create({
    data: {
      productId,
      listingId: listing.id,
      price: Number(ch.price),
      inStock: true,
    },
  });
}
