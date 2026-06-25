import type { FastifyInstance } from "fastify";
import { createPriceCheckQueue, createRedisConnection } from "../../jobs/queue.js";
import { getScanStatus, runFullPriceCheck } from "../../jobs/price-check.job.js";
import { syncNaarCatalog } from "../../services/catalog.js";

export async function reportsRoutes(app: FastifyInstance) {
  app.post("/sync-catalog", async () => {
    try {
      const { imported, source } = await syncNaarCatalog();
      if (!imported) {
        const tried = (await import("../../scrapers/naar-catalog.fetch.js")).catalogApiCandidates();
        return {
          status: "failed",
          imported: 0,
          message:
            "Could not fetch products from NAAR_CATALOG_API or known commerce endpoints. Set NAAR_CATALOG_API in Render env, or use POST /products/import-catalog for one-off imports.",
          tried_urls: tried.slice(0, 6),
          import_hint: "POST /products/import-catalog with data/naar-catalog-seed.json",
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

  app.get("/scan-status", async () => getScanStatus());

  app.post("/run-scan", async (req) => {
    const q = req.query as { limit?: string };
    const limit = Math.min(Math.max(Number(q.limit ?? 10), 1), 25);

    void runFullPriceCheck(limit).catch((err) => {
      req.log.error({ err }, "Background price scan failed");
    });

    return {
      status: "started",
      limit,
      message:
        "Competitor price scan started in the background. Amazon, Flipkart and Meesho are scraped with Playwright — refresh the compare page in 2–5 minutes.",
    };
  });

  app.post("/trigger-price-check", async () => {
    const connection = createRedisConnection();
    const queue = createPriceCheckQueue(connection);
    const job = await queue.add("manual-full-check", {});
    await connection.quit();
    return { status: "queued", jobId: job.id };
  });
}
