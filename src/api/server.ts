import Fastify from "fastify";
import cors from "@fastify/cors";
import { alertsRoutes } from "./routes/alerts.js";
import { comparisonRoutes } from "./routes/comparison.js";
import { productsRoutes } from "./routes/products.js";
import { reportsRoutes } from "./routes/reports.js";
import { config, isProduction } from "../lib/config.js";

const app = Fastify({ logger: true });

await app.register(cors, {
  origin: [config.CORS_ORIGIN, "http://127.0.0.1:3000", "http://localhost:3000"],
  methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
});

app.get("/", async () => ({
  app: "Naar Price Monitor",
  stack: "Node.js 22 · Fastify · Prisma · BullMQ · Transformers.js",
  health: "/health",
  compare_ui: `${config.CORS_ORIGIN}/compare`,
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

await app.listen({ port: config.PORT, host: config.HOST });
console.log(`API listening on http://${config.HOST}:${config.PORT}`);
