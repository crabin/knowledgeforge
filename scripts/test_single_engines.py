from __future__ import annotations

import argparse
import json
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


def build_engines(config: AppConfig) -> dict[str, object]:
    shared_chat_client = OpenAICompatibleChatClient(config.openai, timeout=1.5)
    query_engine = QueryEngine(
        chat_client=shared_chat_client,
        embedding_client=OpenAICompatibleEmbeddingClient(config.openai),
        crawler=DomainKnowledgeCrawler(timeout=1.0),
    )
    return {
        "query": query_engine,
        "insight": InsightEngine(),
        "media": MediaEngine(
            chat_client=shared_chat_client,
            crawler=MediaPerspectiveCrawler(timeout=1.0),
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run single engine smoke tests.")
    parser.add_argument("--engine", choices=["query", "insight", "media", "all"], default="all")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--subdomain", action="append", dest="subdomains", default=[])
    parser.add_argument("--focus-point", action="append", dest="focus_points", default=[])
    parser.add_argument("--time-window", default="近 12 个月")
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
    engines = build_engines(config)
    selected = engines.keys() if args.engine == "all" else [args.engine]

    results = {}
    for name in selected:
        engine = engines[name]
        result = engine.run(context, round_number=1)
        payload = result.to_dict()
        results[name] = payload
        print(f"\n=== {name.upper()} ENGINE ===")
        print(payload["summary"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
