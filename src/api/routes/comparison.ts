import type { FastifyInstance } from "fastify";
import { classifyChannel } from "../../engine/price.comparator.js";
import { prisma } from "../../lib/prisma.js";
import { loadSellers, sellerCount } from "../../scrapers/seller.registry.js";

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

  for (const listing of product.listings) {
    const latest = listing.snapshots.sort((a, b) => b.capturedAt.getTime() - a.capturedAt.getTime())[0];
    const entry = {
      price: latest?.price ?? null,
      url: listing.platformUrl,
      match_score: listing.matchConfidence,
      match_method: listing.matchMethod,
      title: product.name,
      seller_name: listing.sellerName,
    };

    if (listing.platform === "seller") {
      (matches.sellers as unknown[]).push(entry);
    } else {
      matches[listing.platform] = entry;
    }
  }

  const row = {
    sku: product.sku,
    name: product.name,
    variant: product.variant,
    naar_price: product.basePrice,
    naar_url: product.url,
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
    row.channels[platform] = {
      platform,
      price: match.price,
      url: match.url,
      match_confidence: match.match_score,
      match_method: match.match_method,
      ...ch,
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
