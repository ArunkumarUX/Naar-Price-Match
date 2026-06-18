import re

from bs4 import BeautifulSoup


def prepare_html_for_claude(html: str, max_chars: int = 48_000) -> str:
    """Strip noise and truncate HTML before sending to Claude."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "footer", "nav"]):
        tag.decompose()
    text = str(soup)
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_chars:
        return text[:max_chars] + "\n<!-- truncated -->"
    return text
