import Fastify from "fastify";
import cors from "@fastify/cors";
import { alertsRoutes } from "./routes/alerts.js";
import { comparisonRoutes } from "./routes/comparison.js";
import { productsRoutes } from "./routes/products.js";
import { reportsRoutes } from "./routes/reports.js";
import { config, isProduction } from "../lib/config.js";

const app = Fastify({ logger: true });

await app.register(cors, {
  origin: (origin, callback) => {
    const allowed = new Set([
      config.CORS_ORIGIN,
      "http://127.0.0.1:3000",
      "http://localhost:3000",
    ]);
    if (!origin || allowed.has(origin) || /\.vercel\.app$/i.test(origin)) {
      callback(null, true);
      return;
    }
    callback(null, false);
  },
  methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
});

app.get("/", async () => ({
  app: "Naar Price Monitor API",
  status: "ok",
  health: "/health",
  endpoints: {
    health: "GET /health",
    products: "GET /products",
    sync_catalog: "POST /reports/sync-catalog",
    run_scan: "POST /reports/run-scan",
    comparison: "GET /comparison/matrix",
    alerts: "GET /alerts",
  },
}));

app.get("/health", async () => ({
  status: "ok",
  demo_mode: config.DEMO_MODE,
  production_mode: isProduction,
  claude_enabled: false,
  embedding_enabled: true,
  embedding_model: config.EMBEDDING_MODEL,
  claude_model: null,
}));

await app.register(alertsRoutes, { prefix: "/alerts" });
await app.register(productsRoutes, { prefix: "/products" });
await app.register(comparisonRoutes, { prefix: "/comparison" });
await app.register(reportsRoutes, { prefix: "/reports" });

const port = Number(process.env.PORT) || config.PORT;
const host = config.HOST;

await app.listen({ port, host });
console.log(`API listening on http://${host}:${port}`);
