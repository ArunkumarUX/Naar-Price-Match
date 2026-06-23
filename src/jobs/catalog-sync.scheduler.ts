import { config, isProduction } from "../lib/config.js";
import { syncNaarCatalog } from "../services/catalog.js";

const DEFAULT_INTERVAL_MS = 30 * 60 * 1000; // 30 minutes

let timer: ReturnType<typeof setInterval> | null = null;
let syncing = false;

export function startCatalogSyncScheduler() {
  if (timer || config.DEMO_MODE) return;

  const intervalMs = Number(process.env.CATALOG_SYNC_INTERVAL_MS) || DEFAULT_INTERVAL_MS;

  const run = async (reason: string) => {
    if (syncing) return;
    syncing = true;
    try {
      const result = await syncNaarCatalog();
      console.log(`[catalog-sync] ${reason}: imported=${result.imported} source=${result.source ?? "unknown"}`);
    } catch (err) {
      console.error(`[catalog-sync] ${reason} failed`, err);
    } finally {
      syncing = false;
    }
  };

  // Initial sync shortly after boot (Render cold start)
  setTimeout(() => run("startup"), isProduction ? 15_000 : 3_000);
  timer = setInterval(() => run("interval"), intervalMs);
  console.log(`[catalog-sync] scheduler active every ${intervalMs / 60_000} minutes`);
}

export function stopCatalogSyncScheduler() {
  if (timer) clearInterval(timer);
  timer = null;
}
