import { chromium, type Browser, type Page } from "playwright";
import { config } from "../lib/config.js";
import { normalizeNaarProductUrl } from "../lib/naar-url.js";
import { parseNaarCommerceCatalog } from "./naar-catalog.parser.js";
import type { NaarProduct } from "./naar.scraper.js";

function launchOptions() {
  return {
    headless: true,
    ...(config.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: config.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {}),
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  };
}

function looksLikeCatalogPayload(data: unknown): boolean {
  const rows = parseNaarCommerceCatalog(data);
  return rows.length > 0;
}

async function collectFromNetwork(page: Page): Promise<{ products: NaarProduct[]; source: string } | null> {
  const captured: { url: string; data: unknown }[] = [];

  page.on("response", async (response) => {
    try {
      const url = response.url();
      if (response.status() >= 400) return;
      const type = response.headers()["content-type"] ?? "";
      if (!type.includes("json")) return;
      if (!/product|ecommerce|catalog|shop/i.test(url)) return;
      const data = await response.json();
      if (looksLikeCatalogPayload(data)) {
        captured.push({ url, data });
      }
    } catch {
      /* ignore parse errors */
    }
  });

  await page.goto(config.NAAR_SHOP_URL, { waitUntil: "networkidle", timeout: 90_000 });
  await page.waitForTimeout(4_000);

  // Scroll to trigger lazy-loaded product fetches
  for (let i = 0; i < 4; i++) {
    await page.mouse.wheel(0, 1_500);
    await page.waitForTimeout(1_500);
  }

  if (captured.length) {
    const best = captured.sort(
      (a, b) => parseNaarCommerceCatalog(b.data).length - parseNaarCommerceCatalog(a.data).length,
    )[0];
    return {
      products: parseNaarCommerceCatalog(best.data),
      source: `playwright_network:${best.url}`,
    };
  }

  return null;
}

async function collectFromDom(page: Page): Promise<NaarProduct[]> {
  const cards = await page.evaluate(() => {
    const anchors = Array.from(document.querySelectorAll('a[href*="/shop/product/"]'));
    const seen = new Set<string>();
    const rows: { id: string; name: string; price: number; url: string }[] = [];

    for (const anchor of anchors) {
      const el = anchor as HTMLAnchorElement;
      const href = el.href;
      const match = href.match(/\/shop\/product\/([^/?#]+)/);
      if (!match || seen.has(match[1])) continue;
      seen.add(match[1]);

      const card = anchor.closest("article, li, div") ?? anchor;
      const text = (card.textContent ?? "").replace(/\s+/g, " ").trim();
      const name =
        anchor.getAttribute("aria-label") ||
        anchor.querySelector("img")?.getAttribute("alt") ||
        text.split("₹")[0]?.trim() ||
        `Product ${match[1]}`;

      const priceMatch = text.match(/₹\s*([\d,]+(?:\.\d+)?)/);
      const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, "")) : 0;
      if (!name || price <= 0) continue;

      rows.push({ id: match[1], name, price, url: href });
    }
    return rows;
  });

  return cards.map((card) => ({
    sku: card.id,
    name: card.name,
    variant: "default",
    price: card.price,
    url: normalizeNaarProductUrl(card.url, card.name),
    source: "playwright_shop_dom",
  }));
}

/** Scrape live Naar shop — intercepts catalog API responses or reads product cards from DOM. */
export async function scrapeNaarShopLive(): Promise<{ products: NaarProduct[]; source: string } | null> {
  let browser: Browser | null = null;
  try {
    browser = await chromium.launch(launchOptions());
    const page = await browser.newPage({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    });

    const fromNetwork = await collectFromNetwork(page);
    if (fromNetwork?.products.length) {
      return fromNetwork;
    }

    const fromDom = await collectFromDom(page);
    if (fromDom.length) {
      return { products: fromDom, source: "playwright_shop_dom" };
    }

    return null;
  } catch {
    return null;
  } finally {
    await browser?.close();
  }
}
