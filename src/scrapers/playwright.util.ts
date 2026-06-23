import { chromium, type Browser } from "playwright";
import { config } from "../lib/config.js";

export function launchOptions() {
  return {
    headless: true,
    ...(config.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: config.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {}),
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  };
}

let sharedBrowser: Browser | null = null;

export async function getSharedBrowser(): Promise<Browser> {
  if (!sharedBrowser) {
    sharedBrowser = await chromium.launch(launchOptions());
  }
  return sharedBrowser;
}

export async function closeSharedBrowser(): Promise<void> {
  await sharedBrowser?.close();
  sharedBrowser = null;
}
