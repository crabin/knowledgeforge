from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote_plus


@dataclass(slots=True)
class BrowserSearchResult:
    title: str
    url: str
    snippet: str


class AgentBrowserCLI:
    def __init__(self, timeout: float = 20.0, trace: Callable[[str], None] | None = None) -> None:
        self._timeout = timeout
        self._binary = shutil.which("agent-browser")
        self._trace = trace
        self._healthy = self._binary is not None
        self._last_failure_reason = ""

    @property
    def available(self) -> bool:
        return self._binary is not None

    @property
    def healthy(self) -> bool:
        return self.available and self._healthy

    @property
    def last_failure_reason(self) -> str:
        return self._last_failure_reason

    def search_google(self, query: str, limit: int = 5) -> list[BrowserSearchResult]:
        if not self.healthy:
            if self.available and self._last_failure_reason:
                self._log(f"[BROWSER][search] skipped: browser unhealthy reason={self._last_failure_reason}")
            else:
                self._log("[BROWSER][search] skipped: agent-browser binary not found")
            return []
        if not self.available:
            self._log("[BROWSER][search] skipped: agent-browser binary not found")
            return []

        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        # agent-browser eval already JSON-encodes its return value — return the
        # array directly so json.loads gives us a list, not a double-wrapped string.
        js = (
            "Array.from(document.querySelectorAll('div.g')).slice(0, 20)"
            ".map(function(block) {"
            "  var a = block.querySelector('a[href]');"
            "  if (!a) return null;"
            "  var title = block.querySelector('h3');"
            "  var sn = block.querySelector('div.VwiC3b, div.IsZvec, span.aCOpRe');"
            "  return {title: (title ? title.textContent : a.textContent).trim(), url: a.href,"
            "          snippet: sn ? sn.textContent.trim() : ''};"
            "})"
            ".filter(function(x) { return x && x.title && x.url && x.url.indexOf('http') === 0; })"
            f".slice(0, {limit})"
        )
        try:
            self._log(f"[BROWSER][search] open url={search_url} limit={limit}")
            self._run(["open", search_url], timeout=max(self._timeout, 30.0))
            self._run(["wait", "1500"])
            output = self._run(["eval", js])
            payload = json.loads(output)
            if not isinstance(payload, list):
                self._log(f"[BROWSER][search] unexpected payload type={type(payload).__name__}")
                return []
            results = [
                BrowserSearchResult(
                    title=str(item.get("title", "")).strip(),
                    url=str(item.get("url", "")).strip(),
                    snippet=str(item.get("snippet", "")).strip(),
                )
                for item in payload
                if str(item.get("url", "")).strip()
            ]
            self._log(f"[BROWSER][search] results={len(results)}")
            return results
        except Exception as exc:
            self._log(f"[BROWSER][search] failed {exc.__class__.__name__}: {exc}")
            self._mark_unhealthy(f"search:{exc.__class__.__name__}")
            return []
        finally:
            self._close()

    def fetch_text(self, url: str) -> str:
        if not self.healthy:
            if self.available and self._last_failure_reason:
                self._log(f"[BROWSER][fetch] skipped: browser unhealthy reason={self._last_failure_reason} url={url}")
            else:
                self._log(f"[BROWSER][fetch] skipped: agent-browser binary not found url={url}")
            return ""
        if not self.available:
            self._log(f"[BROWSER][fetch] skipped: agent-browser binary not found url={url}")
            return ""

        try:
            self._log(f"[BROWSER][fetch] open url={url}")
            self._run(["open", url], timeout=max(self._timeout, 25.0))
            self._run(["wait", "1500"])
            for selector in ("article", "main", "body"):
                try:
                    self._log(f"[BROWSER][fetch] get text selector={selector}")
                    text = self._run(["get", "text", selector], timeout=max(self._timeout, 25.0))
                except Exception as exc:
                    self._log(f"[BROWSER][fetch] selector failed selector={selector} {exc.__class__.__name__}: {exc}")
                    continue
                cleaned = " ".join(text.split())
                if cleaned:
                    self._log(f"[BROWSER][fetch] text chars={len(cleaned)} selector={selector}")
                    return cleaned[:4000]
            self._log(f"[BROWSER][fetch] no text url={url}")
            return ""
        except Exception as exc:
            self._log(f"[BROWSER][fetch] failed url={url} {exc.__class__.__name__}: {exc}")
            self._mark_unhealthy(f"fetch:{exc.__class__.__name__}")
            return ""
        finally:
            self._close()

    def _run(self, args: list[str], timeout: float | None = None) -> str:
        if not self._binary:
            raise RuntimeError("agent-browser is not available")
        if args and args[0] == "eval":
            command_preview = f"eval <script chars={len(args[1]) if len(args) > 1 else 0}>"
        else:
            command_preview = " ".join(args[:2])
        self._log(f"[BROWSER][cmd] agent-browser {command_preview} timeout={timeout or self._timeout}")
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
            self._log("[BROWSER][cmd] agent-browser close")
            subprocess.run(
                [self._binary, "close"],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:
            pass

    def _mark_unhealthy(self, reason: str) -> None:
        if not self.available:
            return
        self._healthy = False
        self._last_failure_reason = reason
        self._log(f"[BROWSER][health] degraded reason={reason}")

    def _log(self, message: str) -> None:
        if self._trace:
            self._trace(message)
