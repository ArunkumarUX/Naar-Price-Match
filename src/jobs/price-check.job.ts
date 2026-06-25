import { buildComparisonRow } from "../engine/price.comparator.js";
import { matchProduct, toMatchedListing, type MatchCandidate } from "../matcher/product.matcher.js";
import { marketplaceSearchFallback } from "../scrapers/marketplace.urls.js";
import { searchAmazon, searchFlipkart, searchMeesho } from "../scrapers/marketplace.scraper.js";
import { closeSharedBrowser } from "../scrapers/playwright.util.js";
import { searchSellers } from "../scrapers/seller.registry.js";
import { config } from "../lib/config.js";
import { prisma } from "../lib/prisma.js";
import { syncNaarCatalog } from "../services/catalog.js";
import {
  getScanStatus,
  markScanDone,
  markScanFailed,
  markScanProgress,
  markScanStarted,
} from "./scan-status.js";

type Platform = "amazon" | "flipkart" | "meesho";

const PLATFORM_SEARCHERS = {
  amazon: searchAmazon,
  flipkart: searchFlipkart,
  meesho: searchMeesho,
} as const;

async function resolvePlatformMatch(
  platform: Platform,
  naarProduct: { sku: string; name: string; variant?: string },
  search: (query: string, max: number) => Promise<MatchCandidate[]>,
) {
  try {
    const candidates = (await search(naarProduct.name, 3)) as MatchCandidate[];
    const matched = await matchProduct(naarProduct, candidates, config.MIN_MATCH_CONFIDENCE);
    if (matched[0]) return toMatchedListing(matched[0]);

    if (candidates[0]) {
      return {
        ...candidates[0],
        match_score: 0.4,
        match_method: "unverified",
      };
    }
  } catch {
    /* fall through to search link */
  }

  return {
    ...marketplaceSearchFallback(platform, naarProduct.name),
    match_score: 0.35,
    match_method: "search_fallback",
  };
}

export async function runFullPriceCheck(limit = 10) {
  markScanStarted(limit);

  let dbProducts = await prisma.product.findMany({
    where: { isActive: true },
    take: limit,
    orderBy: { updatedAt: "desc" },
  });

  if (!dbProducts.length) {
    const catalog = await syncNaarCatalog();
    if (!catalog.imported) {
      markScanFailed("Naar catalog empty — sync catalog first.");
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

  try {
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
      for (const platform of ["amazon", "flipkart", "meesho"] as const) {
        const search = PLATFORM_SEARCHERS[platform] as (query: string, max: number) => Promise<MatchCandidate[]>;
        matches[platform] = await resolvePlatformMatch(platform, naarProduct, search);
      }

      // Persist marketplace data immediately so refresh shows links/prices while sellers run.
      const partialRow = buildComparisonRow(naarProduct, matches);
      await persistComparisonRow(product.sku, partialRow);

      if (!config.SKIP_SELLER_SCAN && config.SELLER_SCAN_LIMIT > 0) {
        try {
          const sellerCandidates = await searchSellers(product.name, config.SELLER_SCAN_LIMIT);
          const sellerMatched = await matchProduct(
            naarProduct,
            sellerCandidates as MatchCandidate[],
            Math.max(0.35, config.MIN_MATCH_CONFIDENCE - 0.15),
          );
          matches.sellers =
            sellerMatched.length > 0
              ? sellerMatched.slice(0, 5).map(toMatchedListing)
              : sellerCandidates.slice(0, 3).map((c) => ({
                  ...c,
                  match_score: 0.3,
                  match_method: "seller_unverified",
                }));

          const fullRow = buildComparisonRow(naarProduct, matches);
          await persistComparisonRow(product.sku, fullRow);
        } catch {
          /* marketplace data already saved */
        }
      } else {
        matches.sellers = [];
      }

      scanned.push(product.sku);
      count++;
      markScanProgress(count, product.sku);
      if (count >= limit) break;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Price scan failed";
    markScanFailed(message);
    throw err;
  } finally {
    if (config.USE_PLAYWRIGHT) {
      await closeSharedBrowser();
    }
  }

  markScanDone(count, scanned);
  return { scanned: count, skus: scanned };
}

export { getScanStatus };

async function persistComparisonRow(sku: string, row: Record<string, unknown>) {
  const product = await prisma.product.findUnique({ where: { sku } });
  if (!product) return;

  const channels = row.channels as Record<string, unknown>;
  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const ch = channels[platform] as Record<string, unknown> | undefined;
    if (!ch?.price && !ch?.url) continue;
    await saveListingSnapshot(product.id, platform, ch);
  }

  const sellers = (channels.sellers as Record<string, unknown>[]) ?? [];
  for (const s of sellers) {
    if (!s.price && !s.url) continue;
    await saveListingSnapshot(product.id, "seller", s, String(s.seller_name ?? ""));
  }
}

async function saveListingSnapshot(
  productId: string,
  platform: Platform | "seller",
  ch: Record<string, unknown>,
  sellerName?: string,
) {
  const platformUrl = String(ch.url ?? "");
  if (!platformUrl) return;

  const platformId = String(ch.platformId ?? ch.seller_id ?? platform);
  const matchConfidence = Number(ch.match_confidence ?? ch.match_score ?? 0);
  const matchMethod = String(ch.match_method ?? "unknown");
  const price = Number(ch.price ?? 0) || 0;

  let listing = await prisma.productListing.findFirst({
    where: {
      productId,
      platform,
      platformUrl,
      ...(sellerName ? { sellerName } : {}),
    },
    orderBy: { createdAt: "desc" },
  });

  if (!listing) {
    listing = await prisma.productListing.create({
      data: {
        productId,
        platform,
        platformId,
        sellerName: sellerName || null,
        platformUrl,
        matchConfidence,
        matchMethod,
      },
    });
  } else {
    listing = await prisma.productListing.update({
      where: { id: listing.id },
      data: { matchConfidence, matchMethod, platformId },
    });
  }

  await prisma.priceSnapshot.create({
    data: {
      productId,
      listingId: listing.id,
      price,
      inStock: true,
    },
  });
}
