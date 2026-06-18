import { createPriceCheckQueue, createPriceCheckWorker, createRedisConnection, scheduleRepeatableJobs } from "./queue.js";

const connection = createRedisConnection();
const queue = createPriceCheckQueue(connection);

await scheduleRepeatableJobs(queue);

const worker = createPriceCheckWorker(connection);

worker.on("completed", (job, result) => {
  console.log(`[worker] ${job.name} completed`, result);
});

worker.on("failed", (job, err) => {
  console.error(`[worker] ${job?.name} failed`, err);
});

console.log("Naar price-check worker running");
