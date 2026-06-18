import type { FastifyInstance } from "fastify";
import { prisma } from "../../lib/prisma.js";
import { upsertProduct } from "../../services/catalog.js";

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
    const body = req.body as { products?: Record<string, unknown>[] };
    let imported = 0;
    for (const item of body.products ?? []) {
      const name = String(item.name ?? "").trim();
      if (!name) continue;
      const price = parseFloat(String(item.price ?? item.base_price ?? "0").replace(/,/g, ""));
      if (!Number.isFinite(price) || price <= 0) continue;
      await upsertProduct({
        sku: String(item.sku ?? name.slice(0, 40)),
        name,
        variant: String(item.variant ?? "default"),
        price,
        url: String(item.url ?? "https://naar.io/shop"),
        category: item.category ? String(item.category) : undefined,
      });
      imported++;
    }
    return { imported, total: body.products?.length ?? 0 };
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
