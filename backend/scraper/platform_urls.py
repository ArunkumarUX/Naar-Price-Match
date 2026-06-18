from urllib.parse import quote_plus


def amazon_search_url(query: str) -> str:
    return f"https://www.amazon.in/s?k={quote_plus(query)}"


def flipkart_search_url(query: str) -> str:
    return f"https://www.flipkart.com/search?q={quote_plus(query)}"


def meesho_search_url(query: str) -> str:
    return f"https://www.meesho.com/search?q={quote_plus(query)}"


def product_url(platform: str, title: str, fallback: str | None = None) -> str:
    """Prefer a working search URL for demo/synthetic listings."""
    title = (title or "").strip()
    if not title:
        return fallback or ""
    builders = {
        "amazon": amazon_search_url,
        "flipkart": flipkart_search_url,
        "meesho": meesho_search_url,
    }
    builder = builders.get(platform)
    return builder(title) if builder else (fallback or "")


def is_demo_product_url(url: str | None) -> bool:
    if not url:
        return True
    u = url.lower()
    if "example.com" in u:
        return True
    if "amazon" in u and "/dp/b08xyz" in u:
        return True
    if "flipkart.com/p/fk-" in u:
        return True
    if "meesho.com/ms-" in u and "/search" not in u:
        return True
    return False


def normalize_competitor_url(platform: str, title: str, url: str | None) -> str:
    if is_demo_product_url(url):
        return product_url(platform, title, url or "")
    if url and "amazon" in url.lower() and not url.startswith("http"):
        return f"https://www.amazon.in{url}"
    if url and url.startswith("http://amazon."):
        return url.replace("http://amazon.", "https://www.amazon.")
    if url and url.startswith("https://amazon."):
        return url.replace("https://amazon.", "https://www.amazon.")
    return url or product_url(platform, title)
