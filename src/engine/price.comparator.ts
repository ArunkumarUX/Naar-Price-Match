import { config } from "../lib/config.js";

export interface ChannelStatus {
  status: string;
  deviation_pct: number | null;
  label: string;
}

export function classifyChannel(naarPrice: number, channelPrice: number | null | undefined): ChannelStatus {
  if (!channelPrice || channelPrice <= 0) {
    return { status: "missing", deviation_pct: null, label: "Unmatched" };
  }

  const deviation = ((naarPrice - channelPrice) / naarPrice) * 100;

  if (deviation >= config.MAX_PRICE_DEVIATION_PCT) {
    return { status: "lower", deviation_pct: round2(deviation), label: `−${Math.abs(deviation).toFixed(0)}% Lower` };
  }
  if (deviation <= -50) {
    return { status: "higher", deviation_pct: round2(deviation), label: `+${Math.abs(deviation).toFixed(0)}% Higher` };
  }
  if (deviation <= -15) {
    return { status: "violation", deviation_pct: round2(deviation), label: "MAP Violation" };
  }
  return { status: "ok", deviation_pct: round2(deviation), label: "Parity OK" };
}

export function buildComparisonRow(
  product: { sku: string; name: string; variant?: string | null; price?: number; base_price?: number; url?: string },
  matchesByPlatform: Record<string, unknown>,
) {
  const naarPrice = Number(product.price ?? product.base_price ?? 0);
  const channels: Record<string, unknown> = {};
  const row = {
    sku: product.sku,
    name: product.name,
    variant: product.variant,
    naar_price: naarPrice,
    naar_url: product.url,
    channels,
  };

  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const match = matchesByPlatform[platform] as Record<string, unknown> | null | undefined;
    if (!match) {
      channels[platform] = {
        platform,
        price: null,
        url: null,
        status: "missing",
        deviation_pct: null,
        label: "Unmatched",
        match_confidence: null,
      };
      continue;
    }
    const ch = classifyChannel(naarPrice, Number(match.price ?? 0) || null);
    channels[platform] = {
      platform,
      price: match.price ?? null,
      url: match.url ?? null,
      is_search_link: Boolean(match.is_search_link),
      match_confidence: match.match_score ?? null,
      match_method: match.match_method ?? null,
      title: match.title ?? product.name,
      ...ch,
    };
  }

  const sellerMatches = (matchesByPlatform.sellers as Record<string, unknown>[] | undefined) ?? [];
  channels.sellers = sellerMatches.map((sm) => {
    const ch = classifyChannel(naarPrice, sm.price ? Number(sm.price) : null);
    return {
      seller_name: sm.seller_name,
      seller_id: sm.seller_id,
      seller_website: sm.seller_website,
      seller_category: sm.seller_category,
      price: sm.price ?? null,
      url: sm.url ?? sm.seller_website,
      is_search_link: Boolean(sm.is_search_link),
      title: sm.title ?? product.name,
      match_confidence: sm.match_score ?? null,
      ...ch,
    };
  });

  const sellers = channels.sellers as Record<string, unknown>[];
  const pricedSellers = sellers.filter((s) => s.price);
  const bestSeller = pricedSellers.length
    ? pricedSellers.reduce((a, b) => (Number(a.price) < Number(b.price) ? a : b))
    : null;

  const allCompetitors: Record<string, unknown>[] = [];
  for (const platform of ["amazon", "flipkart", "meesho"] as const) {
    const ch = channels[platform] as Record<string, unknown>;
    if (ch?.price) allCompetitors.push({ ...ch, source: platform });
  }
  for (const s of sellers) {
    if (s.price) allCompetitors.push({ ...s, source: "seller" });
  }

  return {
    ...row,
    summary: {
      lowest_competitor: allCompetitors.length
        ? allCompetitors.reduce((a, b) => (Number(a.price) < Number(b.price) ? a : b))
        : null,
      seller_count_matched: pricedSellers.length,
      best_seller: bestSeller,
      has_discrepancy: hasDiscrepancy(channels),
    },
  };
}

function hasDiscrepancy(channels: Record<string, unknown>): boolean {
  for (const platform of ["amazon", "flipkart", "meesho"]) {
    const st = (channels[platform] as Record<string, unknown> | undefined)?.status;
    if (st && st !== "ok" && st !== "missing") return true;
  }
  const sellers = (channels.sellers as Record<string, unknown>[]) ?? [];
  return sellers.some((s) => s.status !== "ok" && s.status !== "missing");
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
