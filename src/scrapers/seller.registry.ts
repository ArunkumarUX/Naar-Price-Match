import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import axios from "axios";

export interface SellerRecord {
  id: string;
  store_name: string;
  business_name: string;
  website: string;
  category: string;
  active: boolean;
}

const __dirname = dirname(fileURLToPath(import.meta.url));

let cache: SellerRecord[] | null = null;

export function loadSellers(): SellerRecord[] {
  if (cache) return cache;
  const paths = [
    join(__dirname, "../../data/sellers.json"),
    join(__dirname, "../../../backend/data/sellers.json"),
  ];
  for (const p of paths) {
    try {
      cache = JSON.parse(readFileSync(p, "utf-8")) as SellerRecord[];
      return cache;
    } catch {
      /* try next */
    }
  }
  cache = [];
  return cache;
}

export function sellerCount(): number {
  return loadSellers().filter((s) => s.active).length;
}

export async function searchSellers(query: string, maxResults = 8) {
  const sellers = loadSellers().filter((s) => s.active && s.website);
  const results = [];
  for (const seller of sellers.slice(0, maxResults)) {
    let price: number | null = null;
    try {
      const res = await axios.get(seller.website, { timeout: 12_000 });
      const m = String(res.data).match(/₹\s*([\d,]+(?:\.\d+)?)/);
      if (m) price = parseFloat(m[1].replace(/,/g, ""));
    } catch {
      /* offline seller site */
    }
    results.push({
      title: query,
      price,
      url: seller.website,
      seller_name: seller.store_name,
      seller_id: seller.id,
      seller_website: seller.website,
      seller_category: seller.category,
      is_search_link: !price,
    });
  }
  return results;
}
