import type { FastifyInstance } from "fastify";
import { classifyChannel } from "../../engine/price.comparator.js";
import { prisma } from "../../lib/prisma.js";
import { normalizeNaarProductUrl } from "../../lib/naar-url.js";
import { loadSellers, sellerCount } from "../../scrapers/seller.registry.js";

type ListingWithSnapshots = {
  platform: string;
  platformUrl: string;
  matchConfidence: number;
  matchMethod: string;
  sellerName: string | null;
  snapshots: { price: number; capturedAt: Date }[];
};

function pickBestListing(listings: ListingWithSnapshots[], platform: string) {
  const candidates = listings.filter((l) => l.platform === platform);
  if (!candidates.length) return null;

  return candidates
    .map((listing) => {
      const latest = listing.snapshots.sort((a, b) => b.capturedAt.getTime() - a.capturedAt.getTime())[0];
      return { listing, latest };
    })
    .sort((a, b) => {
      const aPrice = a.latest?.price && a.latest.price > 0 ? 1 : 0;
      const bPrice = b.latest?.price && b.latest.price > 0 ? 1 : 0;
      if (aPrice !== bPrice) return bPrice - aPrice;
      const aTime = a.latest?.capturedAt.getTime() ?? 0;
      const bTime = b.latest?.capturedAt.getTime() ?? 0;
      return bTime - aTime;
    })[0];
}

function productFromDb(
  product: {
    sku: string;
    name: string;
    variant: string | null;
    basePrice: number;
    url: string;
    listings: {
      platform: string;
      platformUrl: string;
      matchConfidence: number;
      matchMethod: string;
      sellerName: string | null;
      snapshots: { price: number; capturedAt: Date }[];
    }[];
  },
) {
  const matches: Record<string, unknown> = { amazon: null, flipkart: null, meesho: null, sellers: [] as unknown[] };

  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const picked = pickBestListing(product.listings, platform);
    if (!picked) continue;
    const { listing, latest } = picked;
    const price = latest?.price && latest.price > 0 ? latest.price : null;
    matches[platform] = {
      price,
      url: listing.platformUrl,
      match_score: listing.matchConfidence,
      match_method: listing.matchMethod,
      title: product.name,
      is_search_link: listing.matchMethod.includes("search") || listing.platformUrl.includes("/search") || listing.platformUrl.includes("/s?"),
    };
  }

  for (const listing of product.listings.filter((l) => l.platform === "seller")) {
    const latest = listing.snapshots.sort((a, b) => b.capturedAt.getTime() - a.capturedAt.getTime())[0];
    const price = latest?.price && latest.price > 0 ? latest.price : null;
    (matches.sellers as unknown[]).push({
      price,
      url: listing.platformUrl,
      match_score: listing.matchConfidence,
      match_method: listing.matchMethod,
      title: product.name,
      seller_name: listing.sellerName,
    });
  }

  const row = {
    sku: product.sku,
    name: product.name,
    variant: product.variant,
    naar_price: product.basePrice,
    naar_url: normalizeNaarProductUrl(product.url, product.name),
    channels: {} as Record<string, unknown>,
  };

  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const match = matches[platform] as Record<string, unknown> | null;
    if (!match) {
      row.channels[platform] = {
        platform,
        price: null,
        url: null,
        status: "missing",
        deviation_pct: null,
        label: "Unmatched",
        match_confidence: null,
      };
      continue;
    }
    const ch = classifyChannel(product.basePrice, match.price ? Number(match.price) : null);
    const hasUrl = Boolean(match.url);
    row.channels[platform] = {
      platform,
      price: match.price,
      url: match.url,
      match_confidence: match.match_score,
      match_method: match.match_method,
      ...ch,
      ...(hasUrl && !match.price
        ? { status: "pending", label: "Search link", deviation_pct: null }
        : {}),
    };
  }

  row.channels.sellers = ((matches.sellers as Record<string, unknown>[]) ?? []).map((sm) => ({
    ...sm,
    ...classifyChannel(product.basePrice, sm.price ? Number(sm.price) : null),
    match_confidence: sm.match_score,
  }));

  return row;
}

export async function comparisonRoutes(app: FastifyInstance) {
  app.get("/sellers", async () => ({
    count: sellerCount(),
    sellers: loadSellers(),
  }));

  app.get("/matrix", async (req) => {
    const q = req.query as { limit?: string; live?: string };
    const limit = Math.min(Number(q.limit ?? 50), 200);

    const products = await prisma.product.findMany({
      where: { isActive: true },
      take: limit,
      include: {
        listings: { include: { snapshots: { orderBy: { capturedAt: "desc" }, take: 1 } } },
      },
      orderBy: { updatedAt: "desc" },
    });

    const rows = products.map((p) =>
      productFromDb({
        ...p,
        listings: p.listings.map((l) => ({
          ...l,
          snapshots: l.snapshots,
        })),
      }),
    );

    return {
      seller_registry_count: sellerCount(),
      platforms: ["naar", "amazon", "flipkart", "meesho", "seller"],
      products: rows,
      source: rows.length ? "database" : "empty",
    };
  });
}
