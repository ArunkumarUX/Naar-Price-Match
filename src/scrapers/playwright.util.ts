import { chromium, type Browser } from "playwright";
import { config } from "../lib/config.js";

function chromiumPaths(): string[] {
  return [
    config.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
  ].filter(Boolean);
}

export function launchOptions() {
  const executablePath = chromiumPaths()[0];
  return {
    headless: true,
    ...(executablePath ? { executablePath } : {}),
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  };
}

let sharedBrowser: Browser | null = null;
let launchFailed = false;

export async function getSharedBrowser(): Promise<Browser> {
  if (launchFailed) {
    throw new Error("Chromium launch previously failed");
  }
  if (!sharedBrowser) {
    try {
      sharedBrowser = await chromium.launch(launchOptions());
    } catch (err) {
      launchFailed = true;
      throw err;
    }
  }
  return sharedBrowser;
}

export async function closeSharedBrowser(): Promise<void> {
  await sharedBrowser?.close();
  sharedBrowser = null;
}
