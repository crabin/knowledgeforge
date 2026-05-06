from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


SOURCE_PRIORITY_POLICY = """
# 权威来源优先级表

## 通用规则

- 通用概念：S 级优先官方机构说明、教材、学术百科、标准文档；A 级使用 Wikipedia、Britannica。
- 基础科学概念：S 级优先大学教材、学会官网、政府或科研机构官网；A 级使用 Britannica、Stanford Encyclopedia、MIT OCW。
- 数学：S 级优先教材、大学课程讲义、AMS、SIAM；A 级使用 arXiv、Springer、Cambridge、Oxford、MIT OCW。
- 计算机科学理论：S 级优先经典教材、ACM、IEEE、MIT/Stanford/CMU 课程；A 级使用 arXiv、DBLP、Google Scholar、Semantic Scholar。
- Python：S 级优先 docs.python.org、python.org、PEP；A 级使用 PyPI 项目页、官方 GitHub。
- Java：S 级优先 Oracle Java Docs、OpenJDK Docs；A 级使用 JEP、Spring 官方文档。
- Go：S 级优先 go.dev、pkg.go.dev、Go Blog；A 级使用 Go GitHub、官方 proposal。
- JavaScript：S 级优先 MDN、ECMAScript/TC39 标准；A 级使用 Node.js Docs、V8 Blog。
- HTML/CSS/Web API：S 级优先 MDN、WHATWG、W3C；A 级使用 Can I Use、浏览器官方文档。
- TypeScript：S 级优先 TypeScript 官方文档、TypeScript GitHub；A 级使用 Microsoft DevBlogs、DefinitelyTyped。
- React：S 级优先 react.dev；A 级使用 Next.js Docs、React GitHub。
- Vue：S 级优先 vuejs.org；A 级使用 Nuxt Docs、Vue GitHub。
- Node.js：S 级优先 nodejs.org docs；A 级使用 npm docs、V8 Blog。
- Docker：S 级优先 docs.docker.com；A 级使用 Docker GitHub、Compose Spec。
- Kubernetes：S 级优先 kubernetes.io docs；A 级使用 CNCF、Helm Docs、官方 GitHub。
- Linux：S 级优先 man pages、kernel.org、发行版官方文档；A 级使用 Arch Wiki、Ubuntu Docs、Debian Wiki、Red Hat Docs。
- Git：S 级优先 git-scm.com docs；A 级使用 GitHub Docs、GitLab Docs。
- GitHub：S 级优先 docs.github.com、GitHub Blog；A 级使用 GitHub Changelog、官方社区。
- 数据库通用：S 级优先官方数据库文档；A 级使用 ACM/IEEE 数据库论文。
- MySQL：S 级优先 MySQL 官方文档；A 级使用 Percona Blog、Oracle Blog。
- PostgreSQL：S 级优先 postgresql.org docs；A 级使用 PostgreSQL Wiki、官方邮件列表。
- Redis：S 级优先 redis.io docs；A 级使用 Redis GitHub、官方博客。
- MongoDB：S 级优先 MongoDB Docs；A 级使用 MongoDB University、官方博客。
- 前后端框架：S 级优先官方文档、官方示例；A 级使用官方 GitHub、release notes。
- API/协议：S 级优先官方标准、RFC、IETF、W3C、WHATWG；A 级使用 MDN、厂商官方文档。
- 云服务：S 级优先 AWS/Azure/Google Cloud/阿里云/腾讯云官方文档；A 级使用官方架构白皮书、官方博客。
- AI/ML 基础概念：S 级优先教材、课程、论文原文；A 级使用 Stanford CS229、Deep Learning Book、MIT/CMU 课程。
- AI/ML 论文：S 级优先顶会/期刊官网、论文原文、OpenReview；A 级使用 arXiv、Semantic Scholar、Google Scholar。
- 深度学习框架：S 级优先 PyTorch/TensorFlow/Keras/JAX Docs；A 级使用官方 GitHub、官方 tutorials。
- 模型与权重：S 级优先 Hugging Face Model Card、模型官方仓库、论文原文；A 级使用 Papers with Code、官方 demo。
- 数据集：S 级优先数据集官网、原始论文、UCI、Kaggle 原发布者；A 级使用 Hugging Face Datasets、Papers with Code。
- 计算机视觉：S 级优先 CVPR/ICCV/ECCV 论文、arXiv、OpenReview；A 级使用 Papers with Code、官方代码仓库。
- NLP/LLM：S 级优先 ACL Anthology、EMNLP/NAACL/COLING、arXiv、OpenReview；A 级使用 Hugging Face、Papers with Code、模型官方博客。
- 强化学习：S 级优先 NeurIPS/ICML/ICLR、arXiv、OpenReview；A 级使用 Spinning Up、DeepMind Blog、Berkeley/Stanford 课程。
- 网络安全通用：S 级优先 NIST、CISA、MITRE、OWASP、CVE、NVD；A 级使用 ENISA、SANS、USENIX Security、IEEE S&P、ACM CCS。
- 漏洞信息：S 级优先 CVE、NVD、CISA KEV、厂商安全公告；A 级使用 GitHub Security Advisory、Exploit-DB。
- Web 安全：S 级优先 OWASP、PortSwigger Web Security Academy；A 级使用 MDN Security、CWE、CVE/NVD。
- IDS/入侵检测研究：S 级优先 IEEE、ACM、Elsevier、Springer、arXiv；A 级使用 Google Scholar、Semantic Scholar、Papers with Code。
- 恶意软件/威胁情报：S 级优先 MITRE ATT&CK、CISA、Mandiant、Microsoft Security、CrowdStrike；A 级使用 VirusTotal、ANY.RUN、MalwareBazaar。
- 新闻/时事：S 级优先 Reuters、AP、BBC、NHK、Kyodo；A 级使用 The Guardian、Financial Times、Nikkei Asia、CNN。
- 国际新闻：S 级优先 Reuters、AP、BBC；A 级使用 The Guardian、Financial Times、Al Jazeera、Nikkei Asia。
- 日本新闻：S 级优先 NHK、Kyodo、Nikkei、政府官网；A 级使用 Japan Times、Asahi、Mainichi、Yomiuri。
- 中国新闻/政策：S 级优先中国政府网、各部委官网、新华社；A 级使用人民日报、央视、财新。
- 法律/政策：S 级优先政府官网、法规数据库、法院官网、监管机构官网；A 级使用 OECD、UN、EU、World Bank。
- 金融/经济：S 级优先中央银行、财政部、统计局、IMF、World Bank、OECD、SEC；A 级使用 FRED、Trading Economics、Yahoo Finance。
- 股票/公司财务：S 级优先公司 IR、年报、财报、SEC EDGAR；A 级使用 Yahoo Finance、Bloomberg、Reuters。
- 公司/产品信息：S 级优先公司官网、官方文档、官方博客、官方公告；A 级使用 GitHub 官方组织、release notes、status page。
- 开源项目：S 级优先官方 GitHub/GitLab、README、Docs、Release Notes；A 级使用 Issues、Discussions、官方论坛。
- 标准/规范：S 级优先 ISO、IEC、IEEE、IETF RFC、W3C、WHATWG、NIST；A 级使用厂商实现文档、MDN。
- 医学/健康：S 级优先 WHO、CDC、NIH、NHS、Mayo Clinic、PubMed；A 级使用 Cochrane Library、医学期刊。
- 教育/课程：S 级优先大学官网、课程页面、官方教材；A 级使用 MIT OCW、Stanford Online、Coursera 官方课程。
- 地理/旅行：S 级优先官方旅游局、政府网站、Google Maps、交通官网；A 级使用 Wikivoyage、Lonely Planet、Tripadvisor。
- 天气/灾害：S 级优先气象局、JMA、NOAA、政府灾害平台；A 级使用 NHK、当地政府公告。
- 图片/媒体素材：S 级优先 Wikimedia Commons、Unsplash、Pexels、官方媒体库；A 级使用 Getty、Adobe Stock、Pixabay。
- 统计数据：S 级优先政府统计局、World Bank、OECD、UN Data、IMF；A 级使用 Statista、Our World in Data。
- 百科/快速理解：S 级优先 Wikipedia、Britannica、百度百科；A 级使用 Stanford Encyclopedia、Investopedia。
- 问答/社区：S 级优先 Stack Overflow、Stack Exchange、GitHub Issues；A 级使用 Reddit、Hacker News、知乎。
- 中文技术资料：S 级优先官方中文文档、中文翻译文档；A 级使用阿里云/腾讯云/华为云文档、中文社区。
- 论文检索：S 级优先 Google Scholar、Semantic Scholar、OpenAlex、DBLP；A 级使用 ResearchGate、Connected Papers。
- 代码复现：S 级优先官方 GitHub、作者代码仓库、Papers with Code；A 级使用 Colab、Hugging Face Spaces。
- 软件版本/更新：S 级优先官方 release notes、changelog、GitHub releases；A 级使用官方博客、package registry。
- 错误排查：S 级优先官方文档、GitHub Issues、Stack Overflow；A 级使用官方论坛、Discord、邮件列表。

## 简化版优先级公式

- 查定义：官方/教材/标准 > 学术百科 > Wikipedia > 博客。
- 查技术用法：官方文档 > 官方示例 > GitHub Issues > Stack Overflow > 博客。
- 查论文：顶会/期刊正式版 > arXiv > OpenReview > Semantic Scholar / Google Scholar。
- 查模型：论文原文 > 官方仓库 > Hugging Face Model Card > Papers with Code > 测评文章。
- 查数据集：数据集官网 > 原始论文 > Hugging Face/Kaggle 原发布者 > 第三方镜像。
- 查新闻：Reuters/AP/BBC/NHK/政府公告 > 主流媒体 > 当地媒体 > 社交平台。
- 查法律政策：政府/监管机构原文 > 官方解读 > 新闻报道 > 博客解读。
- 查安全漏洞：CVE/NVD/CISA/厂商公告 > MITRE/OWASP > 安全公司报告 > 博客/PoC。
- 查公司产品：官网/官方文档 > 官方博客/公告 > release notes > 社区讨论。
- 查报错：官方文档 > GitHub Issues > Stack Overflow > 博客/论坛。

## 最终判断标准

- 是否是一手来源。
- 是否有明确作者或机构。
- 是否有发布时间或版本号。
- 是否可以被其他来源验证。
- 是否存在商业目的或立场偏向。
- 是否适合当前用途。
- 是否过时。
""".strip()


SYSTEM_PROMPT = """
你是 KnowledgeForge 的查询队列规划助手。你只负责把待查询条目转成可执行的 JSON 查询队列。

必须遵守：
- 只输出 JSON object，不要输出 Markdown。
- 根据权威来源优先级表判断类别、查询目的和来源优先级。
- query_text 必须是短搜索词，格式优先为“领域名 + 知识点/证据主题”，不要写“补充”“查找”“关键依据”等操作性措辞。
- 对技术、政策、新闻、价格、版本、法规、漏洞等时效性强的条目，在 acceptance_criteria 中要求核对发布时间、版本号或发布日期。
- 输出任务必须适配 KnowledgeForge 当前 query task 字段。
""".strip()


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float


def main() -> int:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)

    try:
        query_items = load_query_items(args)
        user_prompt = build_user_prompt(query_items=query_items, domain=args.domain)
        if args.dry_run:
            emit_json(
                {
                    "dry_run": True,
                    "system_prompt": SYSTEM_PROMPT,
                    "user_prompt": user_prompt,
                },
                args.output,
            )
            return 0

        if args.mock_response:
            llm_payload = parse_json_response(Path(args.mock_response).read_text(encoding="utf-8"))
            elapsed_seconds = 0.0
        else:
            config = build_llm_config(args)
            started = time.perf_counter()
            llm_payload = request_query_queue(config, user_prompt)
            elapsed_seconds = time.perf_counter() - started

        queue = normalize_queue(llm_payload, domain=args.domain)
        result = {
            "domain": args.domain,
            "source_policy": "embedded_authority_priority_table",
            "elapsed_seconds": round(elapsed_seconds, 2),
            "total": len(queue),
            "tasks": queue,
            "raw_response": llm_payload if args.include_raw else None,
        }
        if not args.include_raw:
            result.pop("raw_response")
        emit_json(result, args.output)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(f"[FAIL] HTTP {exc.response.status_code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a KnowledgeForge JSON query queue from source-priority policy and query items.",
    )
    parser.add_argument("--domain", default="", help="Optional domain name prepended to generated search terms.")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="One query item. Can be passed multiple times.",
    )
    parser.add_argument(
        "--queries-json",
        default="",
        help="JSON file containing a list of strings or objects with title/query/claim fields.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file to load for OPENAI_* settings.")
    parser.add_argument("--timeout", type=float, default=60.0, help="LLM request timeout seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling the LLM.")
    parser.add_argument("--mock-response", default="", help="Use a saved LLM JSON response instead of calling the LLM.")
    parser.add_argument("--include-raw", action="store_true", help="Include raw LLM JSON in output.")
    parser.add_argument("--output", default="", help="Optional path to write the generated JSON queue.")
    return parser.parse_args()


def load_query_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    loaded: list[Any] = []
    if args.queries_json:
        payload = json.loads(Path(args.queries_json).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("--queries-json must contain a JSON list.")
        loaded.extend(payload)
    loaded.extend(args.query)
    if not loaded:
        raise ValueError("Pass at least one --query or provide --queries-json.")

    items: list[dict[str, Any]] = []
    for index, item in enumerate(loaded, start=1):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            items.append({"id": f"item-{index}", "title": text, "claim_or_gap": text})
            continue
        if not isinstance(item, dict):
            raise ValueError("Query items must be strings or JSON objects.")
        normalized = dict(item)
        normalized.setdefault("id", f"item-{index}")
        normalized.setdefault(
            "title",
            normalized.get("query") or normalized.get("query_text") or normalized.get("claim_or_gap") or "",
        )
        normalized.setdefault("claim_or_gap", normalized.get("title", ""))
        if str(normalized.get("title", "")).strip():
            items.append(normalized)
    if not items:
        raise ValueError("No non-empty query items were provided.")
    return items


def build_user_prompt(*, query_items: list[dict[str, Any]], domain: str) -> str:
    schema = {
        "tasks": [
            {
                "task_id": "source-priority-001",
                "task_type": "query",
                "target_node_id": "optional original item id",
                "section": "证据与来源",
                "claim_or_gap": "需要证据支撑的事实、定义、用法或缺口",
                "query_text": "短搜索词",
                "expected_evidence": ["期望得到的信息"],
                "preferred_source_types": ["official documentation", "paper", "wikipedia"],
                "source_priority": [
                    {
                        "tier": "S",
                        "source_types": ["一手权威来源类型"],
                        "examples": ["具体站点、机构、论文库或文档名"],
                    },
                    {
                        "tier": "A",
                        "source_types": ["高可信补充来源类型"],
                        "examples": ["具体站点、机构、论文库或文档名"],
                    },
                ],
                "authority_queries": ["带 site: 的权威查询词"],
                "acceptance_criteria": ["验收标准"],
                "status": "pending",
            }
        ]
    }
    return "\n\n".join(
        [
            "请根据下面的权威来源优先级表，为待查询列表生成 JSON 查询队列。",
            f"领域名：{domain or '未指定'}",
            "权威来源优先级表：",
            SOURCE_PRIORITY_POLICY,
            "待查询列表 JSON：",
            json.dumps(query_items, ensure_ascii=False, indent=2),
            "输出 JSON schema 示例：",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )


def build_llm_config(args: argparse.Namespace) -> LlmConfig:
    missing = [
        name
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
        if not getenv(name)
    ]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")
    return LlmConfig(
        api_key=getenv("OPENAI_API_KEY", ""),
        base_url=getenv("OPENAI_BASE_URL", "").rstrip("/"),
        model=getenv("OPENAI_MODEL", ""),
        timeout=args.timeout,
    )


def request_query_queue(config: LlmConfig, user_prompt: str) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            f"{config.base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Provider response did not contain choices.")
    content = str(choices[0].get("message", {}).get("content", "")).strip()
    if not content:
        raise RuntimeError("Provider response did not contain message.content.")
    return parse_json_response(content)


def parse_json_response(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object.")
    return payload


def normalize_queue(payload: dict[str, Any], *, domain: str) -> list[dict[str, Any]]:
    raw_tasks = payload.get("tasks") or payload.get("queue") or payload.get("query_tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("LLM response must contain tasks, queue, or query_tasks as a list.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_tasks, start=1):
        if not isinstance(raw, dict):
            continue
        task = dict(raw)
        task_id = str(task.get("task_id", "")).strip() or f"source-priority-{index:03d}"
        if task_id in seen_ids:
            task_id = f"{task_id}-{index:03d}"
        seen_ids.add(task_id)

        query_text = _clean_text(task.get("query_text") or task.get("query") or task.get("title"))
        if domain and query_text and domain.lower() not in query_text.lower():
            query_text = f"{domain} {query_text}"
        claim = _clean_text(task.get("claim_or_gap") or query_text)
        expected = _string_list(task.get("expected_evidence"))
        preferred = _string_list(task.get("preferred_source_types") or task.get("source_priority"))
        criteria = _string_list(task.get("acceptance_criteria"))
        authority_queries = _string_list(task.get("authority_queries"))

        normalized.append(
            {
                "task_id": task_id,
                "task_type": "query",
                "target_node_id": _clean_text(task.get("target_node_id") or task.get("item_id")),
                "section": _clean_text(task.get("section")) or "证据与来源",
                "claim_or_gap": claim,
                "query_text": query_text or claim,
                "expected_evidence": expected or ["官方或高公信力来源", "与查询目标直接相关的说明"],
                "preferred_source_types": preferred or ["official documentation", "wikipedia"],
                "source_priority": task.get("source_priority", []),
                "authority_queries": authority_queries,
                "acceptance_criteria": criteria
                or ["至少得到一条可访问链接", "来源能直接支撑 claim_or_gap"],
                "status": "pending",
            }
        )
    if not normalized:
        raise ValueError("No usable query tasks were returned by the LLM.")
    return normalized


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                compact = ", ".join(
                    part
                    for part in (
                        _clean_text(item.get("tier")),
                        " / ".join(_string_list(item.get("source_types"))),
                        " / ".join(_string_list(item.get("examples"))),
                    )
                    if part
                )
                if compact:
                    result.append(compact)
            else:
                text = _clean_text(item)
                if text:
                    result.append(text)
        return result
    text = _clean_text(value)
    return [text] if text else []


def emit_json(payload: dict[str, Any], output: str) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{text}\n", encoding="utf-8")
        print(f"saved: {output_path}")
        return
    print(text)


if __name__ == "__main__":
    raise SystemExit(main())
