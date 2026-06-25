import { config } from "./config.js";

export type CompetitorScrapeMode = "scraperapi" | "playwright" | "search_links";

export function competitorScrapeMode(): CompetitorScrapeMode {
  if (config.SCRAPERAPI_KEY) return "scraperapi";
  if (config.USE_PLAYWRIGHT) return "playwright";
  return "search_links";
}

export function competitorScrapeSummary() {
  const mode = competitorScrapeMode();
  if (mode === "scraperapi") {
    return {
      mode,
      live_prices: true,
      label: "ScraperAPI (recommended)",
      scan_message:
        "Competitor scan started. Live Amazon, Flipkart and Meesho prices via ScraperAPI — refresh in 1–2 minutes.",
    };
  }
  if (mode === "playwright") {
    return {
      mode,
      live_prices: true,
      label: "Playwright (local / high-memory only)",
      scan_message:
        "Competitor scan started with Playwright. Refresh in 2–5 minutes — may be unstable on Render free tier.",
    };
  }
  return {
    mode,
    live_prices: false,
    label: "Search links only",
    scan_message:
      "Competitor scan started. Search links appear within ~1 minute. For live ₹ prices, add SCRAPERAPI_KEY on Render (best option).",
  };
}
