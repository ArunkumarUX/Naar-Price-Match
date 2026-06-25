import axios from "axios";
import { config } from "../lib/config.js";
import type { ScrapeCandidate } from "./marketplace.scraper.js";

const SCRAPERAPI_ENDPOINT = "http://api.scraperapi.com";

export async function fetchViaScraperApi(url: string): Promise<string | null> {
  if (!config.SCRAPERAPI_KEY) return null;
  try {
    const res = await axios.get(SCRAPERAPI_ENDPOINT, {
      params: {
        api_key: config.SCRAPERAPI_KEY,
        url,
        render: true,
        country_code: "in",
      },
      timeout: 90_000,
    });
    return String(res.data);
  } catch {
    return null;
  }
}

function parsePrice(text: string): number | null {
  const m = text.match(/₹\s*([\d,]+(?:\.\d+)?)/);
  if (!m) return null;
  const n = parseFloat(m[1].replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function parseAmazonSearchHtml(html: string, query: string, maxResults: number): ScrapeCandidate[] {
  const results: ScrapeCandidate[] = [];
  const cardRe = /data-asin="([A-Z0-9]{10})"[\s\S]*?(?=data-asin="|$)/gi;
  let match: RegExpExecArray | null;

  while ((match = cardRe.exec(html)) !== null && results.length < maxResults) {
    const block = match[0];
    const asin = match[1];
    if (!asin || asin === "undefined") continue;

    const titleMatch = block.match(/<span[^>]*class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)</i)
      || block.match(/<h2[^>]*>[\s\S]*?<span[^>]*>([^<]+)</i);
    const title = titleMatch?.[1]?.replace(/&amp;/g, "&").trim() || query;

    const priceMatch = block.match(/class="a-offscreen"[^>]*>\s*₹\s*([\d,]+(?:\.\d+)?)/i)
      || block.match(/₹\s*([\d,]+(?:\.\d+)?)/);
    const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, "")) : null;

    const hrefMatch = block.match(/href="(\/[^"]*\/dp\/[^"?]+)/i);
    const url = hrefMatch ? `https://www.amazon.in${hrefMatch[1]}` : `https://www.amazon.in/dp/${asin}`;

    if (!price || price <= 0) continue;
    results.push({ title, price, url, platformId: asin, is_search_link: false });
  }

  return results;
}

export function parseFlipkartSearchHtml(html: string, query: string, maxResults: number): ScrapeCandidate[] {
  const results: ScrapeCandidate[] = [];
  const seen = new Set<string>();
  const blocks = html.split('data-id="').slice(1);

  for (const block of blocks) {
    if (results.length >= maxResults) break;

    const titleMatch = block.match(/class="[^"]*(?:s1Q9rs|IRpwTa|_4rR01T)[^"]*"[^>]*>([^<]+)</i)
      || block.match(/title="([^"]+)"/i);
    const title = titleMatch?.[1]?.replace(/&amp;/g, "&").trim() || "";

    const priceMatch = block.match(/class="[^"]*_30jeq3[^"]*"[^>]*>\s*₹?([\d,]+)/i)
      || block.match(/₹\s*([\d,]+)/);
    const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, "")) : null;

    const hrefMatch = block.match(/href="(\/[^"]*\/p\/[^"?]+)/i);
    if (!hrefMatch) continue;
    const url = `https://www.flipkart.com${hrefMatch[1]}`;
    if (seen.has(url)) continue;
    seen.add(url);

    if (!title || !price || price <= 0) continue;
    const pid = url.match(/\/p\/([^?]+)/)?.[1] || `flipkart-${results.length}`;
    results.push({ title, price, url, platformId: pid, is_search_link: false });
  }

  return results.length ? results : parseGenericPrices(html, query, "flipkart", maxResults);
}

export function parseMeeshoSearchHtml(html: string, query: string, maxResults: number): ScrapeCandidate[] {
  const results: ScrapeCandidate[] = [];
  const seen = new Set<string>();
  const linkRe = /href="(https:\/\/www\.meesho\.com\/[^"]+)"/gi;
  let linkMatch: RegExpExecArray | null;

  while ((linkMatch = linkRe.exec(html)) !== null && results.length < maxResults) {
    const url = linkMatch[1].split("?")[0];
    if (seen.has(url) || url.endsWith("/search")) continue;

    const start = Math.max(0, linkMatch.index - 400);
    const snippet = html.slice(start, linkMatch.index + 400);
    const titleMatch = snippet.match(/aria-label="([^"]+)"/i) || snippet.match(/>([^<]{8,120})</);
    const title = titleMatch?.[1]?.replace(/&amp;/g, "&").trim() || query;
    const price = parsePrice(snippet);
    if (!price) continue;

    seen.add(url);
    results.push({
      title: title.slice(0, 200),
      price,
      url,
      platformId: `meesho-${results.length}`,
      is_search_link: false,
    });
  }

  return results.length ? results : parseGenericPrices(html, query, "meesho", maxResults);
}

function parseGenericPrices(
  html: string,
  query: string,
  platform: "amazon" | "flipkart" | "meesho",
  maxResults: number,
): ScrapeCandidate[] {
  const price = parsePrice(html);
  if (!price) return [];
  const base =
    platform === "amazon"
      ? "https://www.amazon.in/"
      : platform === "flipkart"
        ? "https://www.flipkart.com/"
        : "https://www.meesho.com/";
  return [
    {
      title: query,
      price,
      url: base,
      is_search_link: true,
      platformId: `${platform}-search`,
    },
  ].slice(0, maxResults);
}

export async function scraperApiSearchPlatform(
  platform: "amazon" | "flipkart" | "meesho",
  searchUrl: string,
  query: string,
  maxResults: number,
): Promise<ScrapeCandidate[]> {
  const html = await fetchViaScraperApi(searchUrl);
  if (!html) return [];

  if (platform === "amazon") return parseAmazonSearchHtml(html, query, maxResults);
  if (platform === "flipkart") return parseFlipkartSearchHtml(html, query, maxResults);
  return parseMeeshoSearchHtml(html, query, maxResults);
}
