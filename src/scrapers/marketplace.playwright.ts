import type { Page } from "playwright";
import { getSharedBrowser } from "./playwright.util.js";
import type { ScrapeCandidate } from "./marketplace.scraper.js";

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

function searchUrl(platform: string, query: string): string {
  const q = encodeURIComponent(query);
  if (platform === "amazon") return `https://www.amazon.in/s?k=${q}`;
  if (platform === "flipkart") return `https://www.flipkart.com/search?q=${q}`;
  if (platform === "meesho") return `https://www.meesho.com/search?q=${q}`;
  return `https://www.google.com/search?q=${q}`;
}

async function newPage(): Promise<Page> {
  const browser = await getSharedBrowser();
  const page = await browser.newPage({ userAgent: USER_AGENT });
  page.setDefaultTimeout(45_000);
  return page;
}

function parsePrice(text: string): number | null {
  const m = text.match(/₹\s*([\d,]+(?:\.\d+)?)/);
  if (!m) return null;
  const n = parseFloat(m[1].replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : null;
}

async function scrapeAmazon(page: Page, query: string, maxResults: number): Promise<ScrapeCandidate[]> {
  await page.goto(searchUrl("amazon", query), { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2_000);

  return page.evaluate(
    ({ max }) => {
      const rows: { title: string; price: number | null; url: string; platformId: string }[] = [];
      const cards = Array.from(document.querySelectorAll('[data-component-type="s-search-result"]')).slice(0, max);
      for (const card of cards) {
        const asin = card.getAttribute("data-asin") || "";
        const titleEl = card.querySelector("h2 a span");
        const title = titleEl?.textContent?.trim() || "";
        const priceEl = card.querySelector(".a-price .a-offscreen");
        const priceText = priceEl?.textContent?.trim() || "";
        const priceMatch = priceText.match(/[\d,]+(?:\.\d+)?/);
        const price = priceMatch ? parseFloat(priceMatch[0].replace(/,/g, "")) : 0;
        const link = card.querySelector("h2 a") as HTMLAnchorElement | null;
        let href = link?.getAttribute("href") || "";
        if (href.startsWith("/")) href = `https://www.amazon.in${href}`;
        if (!title || price <= 0 || !href) continue;
        rows.push({ title, price, url: href, platformId: asin || `amazon-${rows.length}` });
      }
      return rows;
    },
    { max: maxResults },
  );
}

async function scrapeFlipkart(page: Page, query: string, maxResults: number): Promise<ScrapeCandidate[]> {
  await page.goto(searchUrl("flipkart", query), { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2_500);

  return page.evaluate(
    ({ max }) => {
      const rows: { title: string; price: number | null; url: string; platformId: string }[] = [];
      const cards = Array.from(document.querySelectorAll("div[data-id], a[href*='/p/']")).slice(0, max * 4);
      const seen = new Set<string>();
      for (const card of cards) {
        const root = card.closest("div[data-id]") || card;
        const titleEl =
          root.querySelector("a.s1Q9rs, .IRpwTa, ._4rR01T, a[title]") ||
          (card instanceof HTMLAnchorElement ? card : null);
        const title =
          titleEl?.textContent?.trim() ||
          (titleEl instanceof HTMLElement ? titleEl.getAttribute("title") : null) ||
          "";
        const priceEl = root.querySelector("._30jeq3, .Nx9bqj");
        const priceText = priceEl?.textContent?.trim() || root.textContent || "";
        const priceMatch = priceText.match(/₹\s*([\d,]+)/);
        const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, "")) : 0;
        const urlEl = root.querySelector("a[href*='/p/']") as HTMLAnchorElement | null;
        let href = urlEl?.getAttribute("href") || "";
        if (href.startsWith("/")) href = `https://www.flipkart.com${href}`;
        if (!title || price <= 0 || !href || seen.has(href)) continue;
        seen.add(href);
        const pid = href.match(/\/p\/([^?]+)/)?.[1] || `flipkart-${rows.length}`;
        rows.push({ title, price, url: href, platformId: pid });
        if (rows.length >= max) break;
      }
      return rows;
    },
    { max: maxResults },
  );
}

async function scrapeMeesho(page: Page, query: string, maxResults: number): Promise<ScrapeCandidate[]> {
  await page.goto(searchUrl("meesho", query), { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2_500);

  return page.evaluate(
    ({ max }) => {
      const rows: { title: string; price: number | null; url: string; platformId: string }[] = [];
      const cards = Array.from(document.querySelectorAll("a[href*='/'], [data-testid]")).slice(0, max * 6);
      const seen = new Set<string>();
      for (const card of cards) {
        const text = (card.textContent || "").replace(/\s+/g, " ").trim();
        const title =
          card.getAttribute("aria-label") ||
          card.querySelector("p, h2, span")?.textContent?.trim() ||
          text.split("₹")[0]?.trim() ||
          "";
        const priceMatch = text.match(/₹\s*([\d,]+)/);
        const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, "")) : 0;
        const link = (card.closest("a[href]") || (card instanceof HTMLAnchorElement ? card : null)) as HTMLAnchorElement | null;
        let href = link?.href || "";
        if (href && !href.startsWith("http")) href = `https://www.meesho.com${href}`;
        if (!title || price <= 0 || !href || seen.has(href)) continue;
        seen.add(href);
        rows.push({
          title: title.slice(0, 200),
          price,
          url: href,
          platformId: `meesho-${rows.length}`,
        });
        if (rows.length >= max) break;
      }
      return rows;
    },
    { max: maxResults },
  );
}

export async function playwrightSearchPlatform(
  platform: "amazon" | "flipkart" | "meesho",
  query: string,
  maxResults = 3,
): Promise<ScrapeCandidate[]> {
  let page: Page | null = null;
  try {
    page = await newPage();
    const raw =
      platform === "amazon"
        ? await scrapeAmazon(page, query, maxResults)
        : platform === "flipkart"
          ? await scrapeFlipkart(page, query, maxResults)
          : await scrapeMeesho(page, query, maxResults);

    return raw.map((row) => ({
      title: row.title,
      price: row.price,
      url: row.url,
      platformId: row.platformId,
      is_search_link: false,
    }));
  } catch {
    return [];
  } finally {
    await page?.close();
  }
}
