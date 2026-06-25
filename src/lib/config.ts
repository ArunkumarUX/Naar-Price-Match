import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.coerce.number().default(8000),
  HOST: z.string().default("0.0.0.0"),
  DATABASE_URL: z.string().default("postgresql://user:password@localhost:5432/naar_monitor"),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  EMBEDDING_MODEL: z.string().default("Xenova/all-MiniLM-L6-v2"),
  USE_EMBEDDINGS: z.coerce.boolean().default(false),
  MIN_MATCH_CONFIDENCE: z.coerce.number().default(0.75),
  MAX_PRICE_DEVIATION_PCT: z.coerce.number().default(5),
  CRITICAL_DEVIATION_PCT: z.coerce.number().default(20),
  DEMO_MODE: z
    .string()
    .optional()
    .transform((v) => v === "true" || v === "1"),
  NAAR_BASE_URL: z.string().default("https://naar.io"),
  NAAR_SHOP_URL: z.string().default("https://naar.io/shop"),
  NAAR_CATALOG_API: z.string().optional().default(""),
  NAAR_CATALOG_API_KEY: z.string().optional().default(""),
  PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH: z.string().optional().default(""),
  BRIGHTDATA_PROXY: z.string().optional().default(""),
  SCRAPERAPI_KEY: z.string().optional().default(""),
  SKIP_SELLER_SCAN: z.coerce.boolean().default(false),
  SELLER_SCAN_LIMIT: z.coerce.number().default(3),
  SENDGRID_API_KEY: z.string().optional().default(""),
  ALERT_EMAIL_FROM: z.string().default("alerts@naar.io"),
  ALERT_EMAIL_TO: z.string().default("pricing@naar.io"),
  SLACK_WEBHOOK_URL: z.string().optional().default(""),
  CORS_ORIGIN: z.string().default("http://localhost:3000"),
});

export const config = envSchema.parse(process.env);

export const isProduction = config.NODE_ENV === "production" && !config.DEMO_MODE;
