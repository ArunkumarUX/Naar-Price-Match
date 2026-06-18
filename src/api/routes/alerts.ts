import type { FastifyInstance } from "fastify";
import { prisma } from "../../lib/prisma.js";

export async function alertsRoutes(app: FastifyInstance) {
  app.get("/", async (req) => {
    const q = req.query as { severity?: string; resolved?: string; limit?: string; offset?: string };
    const limit = Math.min(Number(q.limit ?? 50), 500);
    const offset = Number(q.offset ?? 0);
    const resolved = q.resolved === "true";

    const alerts = await prisma.priceAlert.findMany({
      where: {
        isResolved: resolved,
        ...(q.severity ? { severity: q.severity as "low" | "medium" | "high" | "critical" } : {}),
      },
      orderBy: { createdAt: "desc" },
      take: limit,
      skip: offset,
    });

    return alerts.map((a) => ({
      id: a.id,
      product_id: a.productId,
      alert_type: a.alertType,
      severity: a.severity,
      naar_price: a.naarPrice,
      competitor_price: a.competitorPrice,
      deviation_pct: a.deviationPct,
      platform: a.platform,
      details: a.details,
      is_resolved: a.isResolved,
      created_at: a.createdAt.toISOString(),
    }));
  });

  app.get("/summary", async () => {
    const rows = await prisma.priceAlert.groupBy({
      by: ["severity"],
      where: { isResolved: false },
      _count: { _all: true },
    });
    return Object.fromEntries(rows.map((r) => [r.severity, r._count._all]));
  });

  app.post("/:alertId/resolve", async (req) => {
    const { alertId } = req.params as { alertId: string };
    await prisma.priceAlert.update({
      where: { id: Number(alertId) },
      data: { isResolved: true, resolvedAt: new Date() },
    });
    return { status: "ok" };
  });
}
