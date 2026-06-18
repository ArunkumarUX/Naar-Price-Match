from rapidfuzz import fuzz


def fuzzy_sku_match(sku_a: str, sku_b: str, threshold: float = 0.88) -> tuple[bool, float]:
    ratio = fuzz.partial_ratio(sku_a, sku_b) / 100
    return ratio >= threshold, ratio
