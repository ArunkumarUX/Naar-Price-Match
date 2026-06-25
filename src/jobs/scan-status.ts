export type ScanPhase = "idle" | "running" | "done" | "failed";

export interface ScanStatus {
  phase: ScanPhase;
  startedAt: string | null;
  finishedAt: string | null;
  scanned: number;
  total: number;
  skus: string[];
  error: string | null;
}

let status: ScanStatus = {
  phase: "idle",
  startedAt: null,
  finishedAt: null,
  scanned: 0,
  total: 0,
  skus: [],
  error: null,
};

export function getScanStatus(): ScanStatus {
  return { ...status };
}

export function markScanStarted(total: number) {
  status = {
    phase: "running",
    startedAt: new Date().toISOString(),
    finishedAt: null,
    scanned: 0,
    total,
    skus: [],
    error: null,
  };
}

export function markScanProgress(scanned: number, sku: string) {
  status = {
    ...status,
    scanned,
    skus: [...status.skus, sku],
  };
}

export function markScanDone(scanned: number, skus: string[]) {
  status = {
    ...status,
    phase: "done",
    finishedAt: new Date().toISOString(),
    scanned,
    skus,
  };
}

export function markScanFailed(error: string) {
  status = {
    ...status,
    phase: "failed",
    finishedAt: new Date().toISOString(),
    error,
  };
}
