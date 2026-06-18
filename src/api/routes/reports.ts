import type { FastifyInstance } from "fastify";
import { createPriceCheckQueue, createRedisConnection } from "../../jobs/queue.js";
import { runFullPriceCheck } from "../../jobs/price-check.job.js";
import { syncNaarCatalog } from "../../services/catalog.js";

export async function reportsRoutes(app: FastifyInstance) {
  app.post("/sync-catalog", async () => {
    try {
      const imported = await syncNaarCatalog();
      if (!imported) {
        return {
          status: "failed",
          imported: 0,
          message:
            "Could not fetch products from naar.io/shop. Set NAAR_CATALOG_API or use POST /products/import-catalog.",
        };
      }
      return { status: "ok", imported, source: "naar" };
    } catch (err) {
      return {
        status: "failed",
        imported: 0,
        message: err instanceof Error ? err.message : "Catalog sync failed",
      };
    }
  });

  app.post("/run-scan", async () => {
    const result = await runFullPriceCheck(25);
    return { status: "completed", ...result };
  });

  app.post("/trigger-price-check", async () => {
    const connection = createRedisConnection();
    const queue = createPriceCheckQueue(connection);
    const job = await queue.add("manual-full-check", {});
    await connection.quit();
    return { status: "queued", jobId: job.id };
  });
}
