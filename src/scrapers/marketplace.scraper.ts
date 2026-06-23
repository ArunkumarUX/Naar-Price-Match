import axios from "axios";
import { config } from "../lib/config.js";
import { playwrightSearchPlatform } from "./marketplace.playwright.js";

export interface ScrapeCandidate {
  title: string;
  price: number | null;
  url: string | null;
  sku?: string;
  platformId?: string;
  is_search_link?: boolean;
}

function searchUrl(platform: string, query: string): string {
  const q = encodeURIComponent(query);
  if (platform === "amazon") return `https://www.amazon.in/s?k=${q}`;
  if (platform === "flipkart") return `https://www.flipkart.com/search?q=${q}`;
  if (platform === "meesho") return `https://www.meesho.com/search?q=${q}`;
  return `https://www.google.com/search?q=${q}`;
}

async function fetchHtml(url: string): Promise<string | null> {
  try {
    if (config.SCRAPERAPI_KEY) {
      const res = await axios.get("http://api.scraperapi.com", {
        params: { api_key: config.SCRAPERAPI_KEY, url, render: true, country_code: "in" },
        timeout: 45_000,
      });
      return String(res.data);
    }
    const res = await axios.get(url, {
      timeout: 20_000,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      },
    });
    return String(res.data);
  } catch {
    return null;
  }
}

function extractFirstPrice(html: string): number | null {
  const m = html.match(/₹\s*([\d,]+(?:\.\d+)?)/);
  if (!m) return null;
  const n = parseFloat(m[1].replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function searchFallback(platform: string, query: string): ScrapeCandidate[] {
  const url = searchUrl(platform, query);
  return [{ title: query, price: null, url, is_search_link: true, platformId: `${platform}-search` }];
}

async function searchPlatform(platform: "amazon" | "flipkart" | "meesho", query: string, maxResults = 3): Promise<ScrapeCandidate[]> {
  const playwrightResults = await playwrightSearchPlatform(platform, query, maxResults);
  if (playwrightResults.length) {
    return playwrightResults.slice(0, maxResults);
  }

  const url = searchUrl(platform, query);
  const html = await fetchHtml(url);
  if (!html) {
    return searchFallback(platform, query);
  }

  const price = extractFirstPrice(html);
  if (!price) {
    return searchFallback(platform, query);
  }

  return [
    {
      title: query,
      price,
      url,
      is_search_link: true,
      platformId: `${platform}-search`,
    },
  ].slice(0, maxResults);
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
