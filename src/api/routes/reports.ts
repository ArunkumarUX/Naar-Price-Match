import type { FastifyInstance } from "fastify";
import { createPriceCheckQueue, createRedisConnection } from "../../jobs/queue.js";
import { runFullPriceCheck } from "../../jobs/price-check.job.js";
import { syncNaarCatalog } from "../../services/catalog.js";

export async function reportsRoutes(app: FastifyInstance) {
  app.post("/sync-catalog", async () => {
    try {
      const { imported, source } = await syncNaarCatalog();
      if (!imported) {
        return {
          status: "failed",
          imported: 0,
          message:
            "Could not fetch products from NAAR_CATALOG_API or known commerce endpoints. Set NAAR_CATALOG_API in Render env, or use POST /products/import-catalog for one-off imports.",
        };
      }
      return { status: "ok", imported, source: source ?? "naar" };
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
