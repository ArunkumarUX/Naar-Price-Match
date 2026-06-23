import { createHash } from "node:crypto";
import { prisma } from "../lib/prisma.js";
import type { NaarProduct } from "../scrapers/naar.scraper.js";

export function productIdForSku(sku: string): string {
  return createHash("sha256").update(sku).digest("hex").slice(0, 16);
}

export async function upsertProduct(input: NaarProduct) {
  const id = productIdForSku(input.sku);
  return prisma.product.upsert({
    where: { sku: input.sku },
    create: {
      id,
      sku: input.sku,
      name: input.name,
      variant: input.variant,
      basePrice: input.price,
      url: input.url,
      category: input.category,
      meta: input.source ? { source: input.source } : undefined,
    },
    update: {
      name: input.name,
      variant: input.variant,
      basePrice: input.price,
      url: input.url,
      category: input.category,
      isActive: true,
      meta: input.source ? { source: input.source } : undefined,
    },
  });
}

export interface CatalogSyncResult {
  imported: number;
  source?: string;
}

export async function syncNaarCatalog(): Promise<CatalogSyncResult> {
  const { scrapeNaarCatalog } = await import("../scrapers/naar.scraper.js");
  let imported = 0;
  let source: string | undefined;

  for await (const product of scrapeNaarCatalog()) {
    source = product.source ?? source;
    await upsertProduct(product);
    imported++;
  }

  return { imported, source };
}
