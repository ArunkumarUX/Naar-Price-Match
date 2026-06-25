import Fuse from "fuse.js";
import { config } from "../lib/config.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let embedder: any = null;
let embeddingUnavailable = false;

async function getEmbedder() {
  if (!config.USE_EMBEDDINGS) return null;
  if (embeddingUnavailable) return null;
  if (!embedder) {
    try {
      const { pipeline } = await import("@xenova/transformers");
      embedder = await pipeline("feature-extraction", config.EMBEDDING_MODEL);
    } catch {
      embeddingUnavailable = true;
      return null;
    }
  }
  return embedder;
}

export interface MatchCandidate {
  title?: string;
  price?: number | null;
  url?: string | null;
  sku?: string;
  platformId?: string;
  seller_name?: string;
  seller_id?: string;
  seller_website?: string;
  seller_category?: string;
  is_search_link?: boolean;
  [key: string]: unknown;
}

export interface MatchResult {
  candidate: MatchCandidate;
  score: number;
  method: string;
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (!na || !nb) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

async function embed(text: string): Promise<number[]> {
  const model = await getEmbedder();
  if (!model) return [];
  const output = await model(text, { pooling: "mean", normalize: true });
  return Array.from(output.data as Float32Array);
}

function normalizeSku(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function variantMatch(variant = "", title = ""): boolean {
  return variant
    .toLowerCase()
    .split(/\s+/)
    .some((t) => t.length > 1 && title.toLowerCase().includes(t));
}

export async function matchProduct(
  naar: { sku: string; name: string; variant?: string },
  candidates: MatchCandidate[],
  minConfidence = config.MIN_MATCH_CONFIDENCE,
): Promise<MatchResult[]> {
  const results: MatchResult[] = [];

  for (const candidate of candidates) {
    let score = 0;
    let method = "no_match";
    let fuseScore = 0;

    const nSku = normalizeSku(naar.sku);
    const cSku = normalizeSku(candidate.sku ?? candidate.platformId ?? "");
    if (nSku && cSku && nSku === cSku) {
      score = 1;
      method = "sku_exact";
    } else {
      const fuse = new Fuse([candidate], { keys: ["title"], includeScore: true });
      const fuseResult = fuse.search(naar.name);
      fuseScore = fuseResult[0] ? 1 - (fuseResult[0].score ?? 1) : 0;

      if (fuseScore >= 0.55) {
        method = "title_fuzzy";
        score = fuseScore;
      } else {
        const [embN, embC] = await Promise.all([
          embed(naar.name),
          embed(candidate.title ?? ""),
        ]);
        if (!embN.length || !embC.length) {
          method = "title_fuzzy";
          score = fuseScore;
        } else {
          const cosine = cosineSimilarity(embN, embC);
          const variantBoost = variantMatch(naar.variant, candidate.title ?? "") ? 0.1 : 0;
          const embeddingScore = Math.min(1, cosine + variantBoost);
          method = embeddingScore > fuseScore * 0.8 ? "embedding" : "title_fuzzy";
          score = Math.max(embeddingScore, fuseScore * 0.8);
        }
      }
    }

    const effectiveMin = candidate.is_search_link ? Math.min(minConfidence, 0.35) : minConfidence;
    if (candidate.is_search_link && fuseScore >= 0.35) {
      score = Math.max(score, 0.5);
      method = "search_link";
    }

    if (score >= effectiveMin) {
      results.push({
        candidate,
        score: Math.round(score * 10_000) / 10_000,
        method,
      });
    }
  }

  return results.sort((a, b) => b.score - a.score);
}

export function toMatchedListing(match: MatchResult) {
  return {
    ...match.candidate,
    match_score: match.score,
    match_method: match.method,
  };
}
