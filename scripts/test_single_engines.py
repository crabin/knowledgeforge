from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


def build_engines(config: AppConfig, *, mode: str) -> dict[str, object]:
    if mode == "live":
        chat_timeout = 8.0
        query_crawler_timeout = 6.0
        media_crawler_timeout = 6.0
    else:
        chat_timeout = 1.5
        query_crawler_timeout = 1.0
        media_crawler_timeout = 1.0

    shared_chat_client = OpenAICompatibleChatClient(config.openai, timeout=chat_timeout)
    query_engine = QueryEngine(
        chat_client=shared_chat_client,
        embedding_client=OpenAICompatibleEmbeddingClient(config.openai),
        crawler=DomainKnowledgeCrawler(timeout=query_crawler_timeout),
    )
    return {
        "query": query_engine,
        "insight": InsightEngine(),
        "media": MediaEngine(
            chat_client=shared_chat_client,
            crawler=MediaPerspectiveCrawler(timeout=media_crawler_timeout),
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
        engine = engines[name]
        result = engine.run(context, round_number=1)
        payload = result.to_dict()
        results[name] = payload
        if not has_live_sources(name, payload):
            fallback_engines.append(name)
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
