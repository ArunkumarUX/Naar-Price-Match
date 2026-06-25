import { config } from "../lib/config.js";
import { marketplaceSearchUrl } from "./marketplace.urls.js";
import { playwrightSearchPlatform } from "./marketplace.playwright.js";
import { scraperApiSearchPlatform } from "./marketplace.scraperapi.js";

export interface ScrapeCandidate {
  title: string;
  price: number | null;
  url: string | null;
  sku?: string;
  platformId?: string;
  is_search_link?: boolean;
}

function searchUrl(platform: string, query: string): string {
  if (platform === "amazon" || platform === "flipkart" || platform === "meesho") {
    return marketplaceSearchUrl(platform, query);
  }
  const q = encodeURIComponent(query);
  return `https://www.google.com/search?q=${q}`;
}

function searchFallback(platform: string, query: string): ScrapeCandidate[] {
  const url = searchUrl(platform, query);
  return [{ title: query, price: null, url, is_search_link: true, platformId: `${platform}-search` }];
}

async function searchPlatform(platform: "amazon" | "flipkart" | "meesho", query: string, maxResults = 3): Promise<ScrapeCandidate[]> {
  try {
    if (config.USE_PLAYWRIGHT) {
      const playwrightResults = await playwrightSearchPlatform(platform, query, maxResults);
      if (playwrightResults.length) {
        return playwrightResults.slice(0, maxResults);
      }
    }

    if (config.SCRAPERAPI_KEY) {
      const url = searchUrl(platform, query);
      const scraperApiResults = await scraperApiSearchPlatform(platform, url, query, maxResults);
      if (scraperApiResults.length) {
        return scraperApiResults.slice(0, maxResults);
      }
    }

    if (!config.SCRAPERAPI_KEY) {
      return searchFallback(platform, query);
    }

    return searchFallback(platform, query);
  } catch {
    return searchFallback(platform, query);
  }
}

export async function searchAmazon(query: string, maxResults = 3) {
  return searchPlatform("amazon", query, maxResults);
}

export async function searchFlipkart(query: string, maxResults = 3) {
  return searchPlatform("flipkart", query, maxResults);
}

export async function searchMeesho(query: string, maxResults = 3) {
  return searchPlatform("meesho", query, maxResults);
}

// Re-export for tests and tooling
export { fetchViaScraperApi } from "./marketplace.scraperapi.js";
