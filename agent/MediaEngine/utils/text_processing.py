from __future__ import annotations

from bs4 import BeautifulSoup


def extract_media_text(html: str, limit: int = 2600) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    candidates = []
    for selector in ("main", "article", "[role='main']", ".content", ".post-content", ".comment", "body"):
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if len(text) > 120:
                candidates.append(text)
    if not candidates:
        text = " ".join(soup.get_text(" ", strip=True).split())
        return text[:limit]
    candidates.sort(key=len, reverse=True)
    return candidates[0][:limit]
