import type { FastifyInstance } from "fastify";
import { prisma } from "../../lib/prisma.js";
import { upsertProduct } from "../../services/catalog.js";
import { parseNaarCommerceCatalog } from "../../scrapers/naar-catalog.parser.js";

export async function productsRoutes(app: FastifyInstance) {
  app.get("/", async (req) => {
    const q = req.query as { limit?: string; offset?: string };
    const limit = Math.min(Number(q.limit ?? 50), 500);
    const offset = Number(q.offset ?? 0);

    const products = await prisma.product.findMany({
      where: { isActive: true },
      take: limit,
      skip: offset,
      orderBy: { updatedAt: "desc" },
    });

    return products.map((p) => ({
      id: p.id,
      sku: p.sku,
      name: p.name,
      variant: p.variant,
      base_price: p.basePrice,
      category: p.category,
      url: p.url,
    }));
  });

  app.post("/import-catalog", async (req) => {
    const body = req.body as unknown;
    const records = parseNaarCommerceCatalog(body);

    for (const product of records) {
      await upsertProduct(product);
    }

    const rawCount = Array.isArray(body)
      ? body.length
      : Array.isArray((body as { products?: unknown[] })?.products)
        ? (body as { products: unknown[] }).products.length
        : records.length;

    return { imported: records.length, total: rawCount, parsed: records.length };
  });

  app.get("/:productId", async (req) => {
    const { productId } = req.params as { productId: string };
    const product = await prisma.product.findFirst({
      where: { OR: [{ id: productId }, { sku: productId }] },
      include: { listings: true },
    });
    if (!product) return { error: "not found" };
    return {
      id: product.id,
      sku: product.sku,
      name: product.name,
      variant: product.variant,
      base_price: product.basePrice,
      category: product.category,
      url: product.url,
      listings: product.listings.map((l) => ({
        platform: l.platform,
        platform_id: l.platformId,
        match_confidence: l.matchConfidence,
        match_method: l.matchMethod,
        url: l.platformUrl,
      })),
    };
  });
}
