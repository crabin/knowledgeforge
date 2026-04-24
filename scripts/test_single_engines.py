from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent.InsightEngine.agent import InsightEngine
from agent.MediaEngine.agent import MediaEngine
from agent.MediaEngine.tools.crawler import MediaPerspectiveCrawler
from agent.QueryEngine.agent import QueryEngine
from agent.QueryEngine.tools.crawler import DomainKnowledgeCrawler
from knowledgeforge.config import AppConfig
from knowledgeforge.intake.context_builder import ContextBuilder
from knowledgeforge.llms.openai_compatible import (
    OpenAICompatibleChatClient,
    OpenAICompatibleEmbeddingClient,
)


def log(message: str) -> None:
    print(message, file=sys.stderr)


def infer_llm_stage(system_prompt: str) -> str:
    lowered = system_prompt.lower()
    if "queryengine 反思器" in system_prompt or "candidate_official_domains" in lowered:
        return "query.reflect"
    if "queryengine 搜索规划器" in system_prompt or "official_queries" in lowered:
        return "query.plan"
    if "queryengine 总结器" in system_prompt or "official_findings" in lowered:
        return "query.summary"
    if "supplementary_social_queries" in lowered and "missing_aspects" in lowered:
        return "media.reflect"
    if "社区观点 / 社交讨论 / 技术博客趋势观察" in system_prompt:
        return "media.plan"
    if "当前观点与未来走向" in system_prompt:
        return "media.summary"
    return "unknown"


class TracedChatClient:
    def __init__(self, inner: OpenAICompatibleChatClient) -> None:
        self._inner = inner

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        stage = infer_llm_stage(system_prompt)
        preview = " ".join(user_prompt.split())[:220]
        log(f"[LLM][{stage}] request")
        log(f"[LLM][{stage}] prompt-preview: {preview}")
        try:
            payload = self._inner.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            keys = ", ".join(sorted(payload.keys()))
            log(f"[LLM][{stage}] response keys: {keys}")
            return payload
        except Exception as exc:
            log(f"[LLM][{stage}] failed: {exc.__class__.__name__}: {exc}")
            raise


class TracedEmbeddingClient:
    def __init__(self, inner: OpenAICompatibleEmbeddingClient) -> None:
        self._inner = inner

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        log(f"[EMBED] request count={len(texts)}")
        try:
            vectors = self._inner.embed_texts(texts)
            dimensions = len(vectors[0]) if vectors else 0
            log(f"[EMBED] response count={len(vectors)} dims={dimensions}")
            return vectors
        except Exception as exc:
            log(f"[EMBED] failed: {exc.__class__.__name__}: {exc}")
            raise


class TracedQueryCrawler:
    def __init__(self, inner: DomainKnowledgeCrawler) -> None:
        self._inner = inner

    def search(
        self,
        *,
        query: str,
        source_type: str,
        official_domains: list[str],
        preferred_domains: list[str] | None = None,
        max_results: int = 5,
    ):
        log(
            f"[QUERY-SEARCH][{source_type}] query={query} official_domains={official_domains or []} "
            f"preferred_domains={preferred_domains or []}"
        )
        hits = self._inner.search(
            query=query,
            source_type=source_type,
            official_domains=official_domains,
            preferred_domains=preferred_domains,
            max_results=max_results,
        )
        if hits:
            for hit in hits[:3]:
                log(f"[QUERY-SEARCH][{source_type}] hit {hit.score:.1f} {hit.url}")
        else:
            log(f"[QUERY-SEARCH][{source_type}] no hits")
        return hits

    def fetch_documents(self, hits, *, max_documents: int = 6):
        log(f"[QUERY-FETCH] fetching {min(len(hits), max_documents)} urls")
        for hit in hits[:max_documents]:
            log(f"[QUERY-FETCH] url={hit.url}")
        docs = self._inner.fetch_documents(hits, max_documents=max_documents)
        log(f"[QUERY-FETCH] fetched documents={len(docs)}")
        return docs


class TracedMediaCrawler:
    def __init__(self, inner: MediaPerspectiveCrawler) -> None:
        self._inner = inner

    def search(
        self,
        *,
        query: str,
        platform_type: str,
        is_technical: bool,
        max_results: int = 5,
    ):
        log(f"[MEDIA-SEARCH][{platform_type}] query={query} is_technical={is_technical}")
        hits = self._inner.search(
            query=query,
            platform_type=platform_type,
            is_technical=is_technical,
            max_results=max_results,
        )
        if hits:
            for hit in hits[:3]:
                log(f"[MEDIA-SEARCH][{platform_type}] hit {hit.score:.1f} {hit.url}")
        else:
            log(f"[MEDIA-SEARCH][{platform_type}] no hits")
        return hits

    def fetch_documents(self, hits, *, max_documents: int = 8):
        log(f"[MEDIA-FETCH] fetching {min(len(hits), max_documents)} urls")
        for hit in hits[:max_documents]:
            log(f"[MEDIA-FETCH] url={hit.url}")
        docs = self._inner.fetch_documents(hits, max_documents=max_documents)
        log(f"[MEDIA-FETCH] fetched documents={len(docs)}")
        return docs


def build_engines(config: AppConfig, *, mode: str) -> dict[str, object]:
    if mode == "live":
        chat_timeout = 8.0
        query_crawler_timeout = 6.0
        media_crawler_timeout = 6.0
    else:
        chat_timeout = 1.5
        query_crawler_timeout = 1.0
        media_crawler_timeout = 1.0

    shared_chat_client = TracedChatClient(OpenAICompatibleChatClient(config.openai, timeout=chat_timeout))
    query_engine = QueryEngine(
        chat_client=shared_chat_client,
        embedding_client=TracedEmbeddingClient(OpenAICompatibleEmbeddingClient(config.openai)),
        crawler=TracedQueryCrawler(DomainKnowledgeCrawler(timeout=query_crawler_timeout)),
    )
    return {
        "query": query_engine,
        "insight": InsightEngine(),
        "media": MediaEngine(
            chat_client=shared_chat_client,
            crawler=TracedMediaCrawler(MediaPerspectiveCrawler(timeout=media_crawler_timeout)),
        ),
    }


def has_live_sources(engine_name: str, payload: dict[str, object]) -> bool:
    if engine_name == "insight":
        return True
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", ""))
        publisher = str(source.get("publisher", ""))
        if url.startswith("http") and "example.com" not in url and publisher not in {"query-plan", "media-plan"}:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run single engine live tests.")
    parser.add_argument("--engine", choices=["query", "insight", "media", "all"], default="all")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--subdomain", action="append", dest="subdomains", default=[])
    parser.add_argument("--focus-point", action="append", dest="focus_points", default=[])
    parser.add_argument("--time-window", default="近 12 个月")
    parser.add_argument("--mode", choices=["live", "smoke"], default="live")
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow query/media engines to return fallback planning output without exiting non-zero.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = AppConfig.from_env(".env")
    log(f"[CONFIG] mode={args.mode} engine={args.engine} allow_fallback={args.allow_fallback}")
    log(f"[CONFIG] domain={args.domain} subdomains={args.subdomains or []} focus_points={args.focus_points or []}")
    builder = ContextBuilder()
    context = builder.build(
        {
            "domain": args.domain,
            "subdomains": args.subdomains,
            "focus_points": args.focus_points,
            "time_window": args.time_window,
        }
    )
    engines = build_engines(config, mode=args.mode)
    selected = engines.keys() if args.engine == "all" else [args.engine]

    results = {}
    fallback_engines: list[str] = []
    for name in selected:
        log(f"[RUN] start engine={name}")
        engine = engines[name]
        result = engine.run(context, round_number=1)
        payload = result.to_dict()
        results[name] = payload
        if not has_live_sources(name, payload):
            fallback_engines.append(name)
            log(f"[RUN] engine={name} fell back to planning output")
        else:
            log(f"[RUN] engine={name} returned live sources")
        print(f"\n=== {name.upper()} ENGINE ===")
        print(payload["summary"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if fallback_engines and not args.allow_fallback:
        engines_text = ", ".join(fallback_engines)
        print(
            f"\n[ERROR] These engines did not return live sources and fell back to planning output: {engines_text}",
            file=sys.stderr,
        )
        print(
            "[ERROR] Re-run with stronger network conditions or pass --allow-fallback if you only want a smoke test.",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
