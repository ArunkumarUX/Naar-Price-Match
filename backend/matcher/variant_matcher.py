import re


def extract_variant_tokens(variant: str) -> list[str]:
    if not variant or variant == "default":
        return []
    return [t for t in re.sub(r"[^a-z0-9\s/]", "", variant.lower()).split() if len(t) > 1]


def variant_overlap_score(variant: str, title: str) -> float:
    tokens = extract_variant_tokens(variant)
    if not tokens:
        return 0.0
    title_lower = title.lower()
    hits = sum(1 for t in tokens if t in title_lower)
    return hits / len(tokens)
