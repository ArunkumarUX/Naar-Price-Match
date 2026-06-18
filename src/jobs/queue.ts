import { Redis, type RedisOptions } from "ioredis";
import { Queue, Worker, type ConnectionOptions } from "bullmq";
import { config } from "../lib/config.js";
import { runFullPriceCheck } from "./price-check.job.js";
import { syncNaarCatalog } from "../services/catalog.js";

export const PRICE_CHECK_QUEUE = "price-check";

export function createRedisConnection() {
  return new Redis(config.REDIS_URL, { maxRetriesPerRequest: null } satisfies RedisOptions);
}

export function createPriceCheckQueue(connection: Redis) {
  return new Queue(PRICE_CHECK_QUEUE, { connection: connection as unknown as ConnectionOptions });
}

export async function scheduleRepeatableJobs(queue: Queue) {
  await queue.add(
    "daily-full-check",
    {},
    {
      repeat: { pattern: "0 2 * * *", tz: "Asia/Kolkata" },
      removeOnComplete: 100,
      removeOnFail: 50,
    },
  );

  await queue.add(
    "critical-refresh",
    { onlyCritical: true },
    {
      repeat: { pattern: "15 */4 * * *", tz: "Asia/Kolkata" },
      removeOnComplete: 100,
      removeOnFail: 50,
    },
  );
}

export function createPriceCheckWorker(connection: Redis) {
  return new Worker(
    PRICE_CHECK_QUEUE,
    async (job) => {
      if (job.name === "sync-catalog") {
        const imported = await syncNaarCatalog();
        return { imported };
      }
      const onlyCritical = Boolean(job.data?.onlyCritical);
      const limit = onlyCritical ? 10 : 25;
      return runFullPriceCheck(limit);
    },
    { connection: connection as unknown as ConnectionOptions },
  );
}
