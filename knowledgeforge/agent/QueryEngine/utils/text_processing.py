from __future__ import annotations

from bs4 import BeautifulSoup


def extract_main_text(html: str, limit: int = 3000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    candidates = []
    for selector in ("main", "article", ".content", ".documentation", "body"):
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if len(text) > 200:
                candidates.append(text)
    if not candidates:
        text = " ".join(soup.get_text(" ", strip=True).split())
        return text[:limit]
    candidates.sort(key=len, reverse=True)
    return candidates[0][:limit]
