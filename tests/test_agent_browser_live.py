from __future__ import annotations

import json
import os
import shutil
import subprocess
import signal
from dataclasses import dataclass
from urllib.parse import quote_plus

import pytest


@dataclass
class AgentBrowserResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def run_agent_browser(*args: str, timeout: float = 30.0) -> AgentBrowserResult:
    binary = shutil.which("agent-browser")
    if binary is None:
        raise AssertionError("agent-browser is not installed or not on PATH")
    process = subprocess.Popen(
        [binary, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return AgentBrowserResult(
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return AgentBrowserResult(
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )


def close_current_page(timeout: float = 10.0) -> None:
    """Close the current browser page but keep the daemon alive."""
    run_agent_browser("close", timeout=timeout)


def close_daemon(timeout: float = 15.0) -> None:
    """Shut down the daemon entirely — use only at session teardown."""
    run_agent_browser("close", "--all", timeout=timeout)


@pytest.fixture(scope="module", autouse=True)
def browser_daemon():
    """Ensure daemon is warm before tests; shut it down after."""
    run_agent_browser("open", "about:blank", timeout=60.0)
    yield
    close_daemon()


def test_agent_browser_can_open_search_page_and_extract_results() -> None:
    close_current_page()
    query = "machine learning"
    # fulltext=Search forces the results page (avoids redirect to the article)
    search_url = (
        f"https://en.wikipedia.org/w/index.php"
        f"?search={quote_plus(query)}&fulltext=Search&ns0=1"
    )

    open_result = run_agent_browser("open", search_url, timeout=60.0)
    assert not open_result.timed_out, "agent-browser open timed out on Wikipedia search"
    assert open_result.returncode == 0, open_result.stderr or open_result.stdout

    wait_result = run_agent_browser("wait", "1500", timeout=10.0)
    assert not wait_result.timed_out, "agent-browser wait timed out after opening search page"
    assert wait_result.returncode == 0, wait_result.stderr or wait_result.stdout

    # Return the array directly — agent-browser eval JSON-encodes its return value,
    # so wrapping in JSON.stringify would produce a double-encoded string.
    js = """
Array.from(document.querySelectorAll('li.mw-search-result')).slice(0, 5).map((result) => {
  const anchor = result.querySelector('.mw-search-result-heading a');
  const snippet = result.querySelector('.searchresult');
  return {
    title: anchor ? anchor.textContent.trim() : '',
    url: anchor ? anchor.href : '',
    snippet: snippet ? snippet.textContent.trim() : ''
  };
}).filter((item) => item.url)
""".strip()
    eval_result = run_agent_browser("eval", js, timeout=20.0)
    assert not eval_result.timed_out, "agent-browser eval timed out while extracting search results"
    assert eval_result.returncode == 0, eval_result.stderr or eval_result.stdout

    payload = json.loads(eval_result.stdout.strip() or "[]")
    assert isinstance(payload, list)
    assert payload, "agent-browser opened search page but extracted no search results"
    assert any(str(item.get("url", "")).startswith("http") for item in payload)

    close_current_page()


def test_agent_browser_can_fetch_page_text() -> None:
    close_current_page()
    target_url = "https://langchain-ai.github.io/langgraph/"

    open_result = run_agent_browser("open", target_url, timeout=60.0)
    assert not open_result.timed_out, "agent-browser open timed out on the LangGraph site"
    assert open_result.returncode == 0, open_result.stderr or open_result.stdout

    wait_result = run_agent_browser("wait", "1500", timeout=10.0)
    assert not wait_result.timed_out, "agent-browser wait timed out after opening the LangGraph site"
    assert wait_result.returncode == 0, wait_result.stderr or wait_result.stdout

    text_result = run_agent_browser("get", "text", "body", timeout=20.0)
    assert not text_result.timed_out, "agent-browser get text timed out on the LangGraph site"
    assert text_result.returncode == 0, text_result.stderr or text_result.stdout

    text = " ".join(text_result.stdout.split())
    assert text, "agent-browser fetched page but returned empty body text"
    assert "langgraph" in text.lower()

    close_current_page()
