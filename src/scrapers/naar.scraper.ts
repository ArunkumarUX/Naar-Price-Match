import { chromium } from "playwright";
import { config } from "../lib/config.js";
import { fetchNaarCommerceCatalog } from "./naar-catalog.fetch.js";

export interface NaarProduct {
  sku: string;
  name: string;
  variant: string;
  price: number;
  url: string;
  category?: string;
  source?: string;
}

export async function* scrapeNaarCatalog(): AsyncGenerator<NaarProduct> {
  const apiCatalog = await fetchNaarCommerceCatalog();
  if (apiCatalog) {
    for (const product of apiCatalog.products) {
      yield { ...product, source: product.source ?? apiCatalog.source };
    }
    return;
  }

  const shopifyUrl = `${config.NAAR_BASE_URL}/products.json?limit=250`;
  try {
    const res = await fetch(shopifyUrl);
    if (res.ok) {
      const data = (await res.json()) as {
        products?: {
          title: string;
          handle: string;
          variants?: { id: number; sku?: string; title?: string; price: string }[];
        }[];
      };
      for (const product of data.products ?? []) {
        for (const variant of product.variants ?? []) {
          yield {
            sku: variant.sku || String(variant.id),
            name: product.title,
            variant: variant.title ?? "default",
            price: parseFloat(variant.price),
            url: `${config.NAAR_BASE_URL}/products/${product.handle}`,
            source: "shopify_json",
          };
        }
      }
      return;
    }
  } catch {
    /* fall through */
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto(`${config.NAAR_BASE_URL}/collections/all`, {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });

    const links = await page.$$eval("a[href*='/products/']", (els) =>
      [...new Set(els.map((e) => (e as { href: string }).href))],
    );

    for (const link of links.slice(0, 100)) {
      await page.goto(link, { waitUntil: "domcontentloaded", timeout: 30_000 });
      const jsonLd = await page
        .$eval("script[type='application/ld+json']", (el) => el.textContent ?? "")
        .catch(() => "");

      if (!jsonLd) continue;

      try {
        const data = JSON.parse(jsonLd) as {
          sku?: string;
          productID?: string;
          name?: string;
          offers?: { name?: string; price?: string } | { name?: string; price?: string }[];
        };
        const offers = Array.isArray(data.offers) ? data.offers : data.offers ? [data.offers] : [];
        for (const offer of offers) {
          const price = parseFloat(offer.price ?? "0");
          if (!data.name || price <= 0) continue;
          yield {
            sku: data.sku ?? data.productID ?? data.name.slice(0, 40),
            name: data.name,
            variant: offer.name ?? "default",
            price,
            url: link,
            source: "playwright_ldjson",
          };
        }
      } catch {
        /* skip malformed JSON-LD */
      }
    }
  } finally {
    await browser.close();
  }
}
