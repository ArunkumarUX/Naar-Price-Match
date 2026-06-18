from __future__ import annotations

import logging
import re

import numpy as np
from rapidfuzz import fuzz

from config import settings

logger = logging.getLogger(__name__)


class ProductMatcher:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.model = None
        self._cache: dict[str, np.ndarray] = {}

        if settings.USE_EMBEDDINGS:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model: %s", self.model_name)
                self.model = SentenceTransformer(self.model_name)
            except Exception as exc:
                logger.warning("Embedding model unavailable: %s — using fuzzy-only matching", exc)

    def match(
        self,
        naar_product: dict,
        candidates: list[dict],
        min_confidence: float | None = None,
    ) -> list[dict]:
        threshold = min_confidence if min_confidence is not None else settings.MIN_MATCH_CONFIDENCE
        scored: list[dict] = []
        for candidate in candidates:
            score, method = self._score(naar_product, candidate)
            if score >= threshold:
                scored.append({**candidate, "match_score": round(score, 4), "match_method": method})
        return sorted(scored, key=lambda x: x["match_score"], reverse=True)

    async def match_async(
        self,
        naar_product: dict,
        candidates: list[dict],
        min_confidence: float | None = None,
    ) -> list[dict]:
        """Fuzzy pre-filter → Claude verification in production."""
        threshold = min_confidence if min_confidence is not None else settings.MIN_MATCH_CONFIDENCE

        if not candidates:
            return []

        if settings.claude_enabled:
            from matcher.claude_matcher import claude_match_products

            claude_results = await claude_match_products(naar_product, candidates, threshold)
            if claude_results:
                return claude_results
            if settings.is_production:
                return []

        return self.match(naar_product, candidates, threshold)

    def _score(self, naar: dict, candidate: dict) -> tuple[float, str]:
        n_sku = self._norm_sku(naar.get("sku", ""))
        c_sku = self._norm_sku(candidate.get("sku", "") or candidate.get("platform_id", ""))
        if n_sku and c_sku and n_sku == c_sku:
            return 1.0, "sku_exact"

        if n_sku and c_sku:
            ratio = fuzz.partial_ratio(n_sku, c_sku) / 100
            if ratio >= 0.88:
                return ratio * 0.95, "sku_fuzzy"

        n_title = self._clean(naar.get("name", ""))
        c_title = self._clean(candidate.get("title", ""))
        if n_title and c_title and self.model is not None:
            try:
                from sentence_transformers import util

                emb_n = self._embed(n_title)
                emb_c = self._embed(c_title)
                cosine = float(util.cos_sim(emb_n, emb_c)[0][0])
                boost = self._variant_boost(naar, candidate)
                return min(1.0, cosine * 0.85 + boost), "embedding"
            except Exception:
                pass

        raw_n = naar.get("name", "")
        raw_c = candidate.get("title", "")
        if raw_n and raw_c:
            ratio = fuzz.token_set_ratio(raw_n, raw_c) / 100
            boost = self._variant_boost(naar, candidate)
            return min(1.0, ratio * 0.75 + boost), "title_fuzzy"

        return 0.0, "no_match"

    def _embed(self, text: str):
        if text not in self._cache:
            self._cache[text] = self.model.encode(text, convert_to_tensor=True)
        return self._cache[text]

    def _variant_boost(self, naar: dict, candidate: dict) -> float:
        variant = re.sub(r"[^a-z0-9\s]", "", (naar.get("variant") or "").lower())
        c_title = candidate.get("title", "").lower()
        if not variant or variant == "default":
            return 0.05
        for token in variant.split():
            if len(token) > 1 and token in c_title:
                return 0.13
        return 0.0

    @staticmethod
    def _norm_sku(sku: str) -> str:
        return re.sub(r"[^a-z0-9]", "", sku.lower())

    @staticmethod
    def _clean(title: str) -> str:
        stopwords = {"the", "and", "for", "with", "of", "in", "a", "an", "by", "at"}
        tokens = re.sub(r"[^a-z0-9\s]", "", title.lower()).split()
        return " ".join(t for t in tokens if t not in stopwords)
