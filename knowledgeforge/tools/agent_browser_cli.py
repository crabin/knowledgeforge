from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(slots=True)
class BrowserSearchResult:
    title: str
    url: str
    snippet: str


class AgentBrowserCLI:
    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout
        self._binary = shutil.which("agent-browser")

    @property
    def available(self) -> bool:
        return self._binary is not None

    def search_duckduckgo(self, query: str, limit: int = 5) -> list[BrowserSearchResult]:
        if not self.available:
            return []

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        js = f"""
JSON.stringify(
  Array.from(document.querySelectorAll('.result')).slice(0, {limit}).map((result) => {{
    const anchor = result.querySelector('.result__title a') || result.querySelector('a.result__a');
    const snippet = result.querySelector('.result__snippet');
    return {{
      title: anchor ? anchor.textContent.trim() : '',
      url: anchor ? anchor.href : '',
      snippet: snippet ? snippet.textContent.trim() : ''
    }};
  }}).filter((item) => item.url)
)
""".strip()
        try:
            self._run(["open", search_url])
            self._run(["wait", "1500"])
            output = self._run(["eval", js])
            payload = json.loads(output)
            return [
                BrowserSearchResult(
                    title=str(item.get("title", "")).strip(),
                    url=str(item.get("url", "")).strip(),
                    snippet=str(item.get("snippet", "")).strip(),
                )
                for item in payload
                if str(item.get("url", "")).strip()
            ]
        except Exception:
            return []
        finally:
            self._close()

    def fetch_text(self, url: str) -> str:
        if not self.available:
            return ""

        try:
            self._run(["open", url], timeout=max(self._timeout, 25.0))
            self._run(["wait", "1500"])
            for selector in ("article", "main", "body"):
                try:
                    text = self._run(["get", "text", selector], timeout=max(self._timeout, 25.0))
                except Exception:
                    continue
                cleaned = " ".join(text.split())
                if cleaned:
                    return cleaned[:4000]
            return ""
        except Exception:
            return ""
        finally:
            self._close()

    def _run(self, args: list[str], timeout: float | None = None) -> str:
        if not self._binary:
            raise RuntimeError("agent-browser is not available")
        completed = subprocess.run(
            [self._binary, *args],
            text=True,
            capture_output=True,
            timeout=timeout or self._timeout,
            check=True,
        )
        return completed.stdout.strip()

    def _close(self) -> None:
        if not self._binary:
            return
        try:
            subprocess.run(
                [self._binary, "close"],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:
            pass
