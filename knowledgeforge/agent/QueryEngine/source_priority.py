from __future__ import annotations

import json
import re
from typing import Any

from knowledgeforge.agent.QueryEngine.utils.ranking import build_site_constrained_queries, domains_for_source_priority


SOURCE_PRIORITY_POLICY = """
# 权威来源优先级表

## 类别优先级

- 通用概念：S 级优先官方机构说明、教材、学术百科、标准文档；A 级使用 Wikipedia、Britannica。
- 基础科学概念：S 级优先大学教材、学会官网、政府或科研机构官网；A 级使用 Britannica、Stanford Encyclopedia、MIT OCW。
- 数学：S 级优先教材、大学课程讲义、AMS、SIAM；A 级使用 arXiv、Springer、Cambridge、Oxford、MIT OCW。
- 计算机科学理论：S 级优先经典教材、ACM、IEEE、MIT/Stanford/CMU 课程；A 级使用 arXiv、DBLP、Google Scholar、Semantic Scholar。
- 编程语言与 Web 技术：S 级优先官方文档、标准、官方示例；A 级使用官方 GitHub、release notes、MDN、Node.js/V8 Blog。
- Python：S 级优先 docs.python.org、python.org、PEP；A 级使用 PyPI 项目页、官方 GitHub。
- Java：S 级优先 Oracle Java Docs、OpenJDK Docs；A 级使用 JEP、Spring 官方文档。
- Go：S 级优先 go.dev、pkg.go.dev、Go Blog；A 级使用 Go GitHub、官方 proposal。
- JavaScript/HTML/CSS/Web API：S 级优先 MDN、ECMAScript/TC39、WHATWG、W3C；A 级使用 Can I Use、浏览器官方文档。
- React/Vue/Node.js/Docker/Kubernetes/Linux/Git/GitHub：S 级优先官方文档；A 级使用官方 GitHub、release notes、官方博客、发行版文档。
- 数据库：S 级优先官方数据库文档；A 级使用 ACM/IEEE 数据库论文、官方 Wiki、官方邮件列表。
- API/协议/标准：S 级优先 RFC、IETF、W3C、WHATWG、ISO、IEC、IEEE、NIST；A 级使用厂商实现文档、MDN。
- 云服务：S 级优先 AWS/Azure/Google Cloud/阿里云/腾讯云官方文档；A 级使用官方架构白皮书、官方博客。
- AI/ML 基础概念：S 级优先教材、课程、论文原文；A 级使用 Stanford CS229、Deep Learning Book、MIT/CMU 课程。
- AI/ML 论文：S 级优先顶会/期刊官网、论文原文、OpenReview；A 级使用 arXiv、Semantic Scholar、Google Scholar。
- 深度学习框架：S 级优先 PyTorch/TensorFlow/Keras/JAX Docs；A 级使用官方 GitHub、官方 tutorials。
- 模型与权重：S 级优先 Hugging Face Model Card、模型官方仓库、论文原文；A 级使用 Papers with Code、官方 demo。
- 数据集：S 级优先数据集官网、原始论文、UCI、Kaggle 原发布者；A 级使用 Hugging Face Datasets、Papers with Code。
- 计算机视觉/NLP/LLM/强化学习：S 级优先顶会/期刊论文、arXiv、OpenReview、ACL Anthology；A 级使用 Hugging Face、Papers with Code、官方代码仓库。
- 网络安全/漏洞/Web 安全：S 级优先 NIST、CISA、MITRE、OWASP、CVE、NVD、厂商安全公告；A 级使用 GitHub Security Advisory、Exploit-DB、PortSwigger。
- 新闻/时事：S 级优先 Reuters、AP、BBC、NHK、Kyodo、政府公告；A 级使用 The Guardian、Financial Times、Nikkei Asia、CNN。
- 法律/政策：中国政府网、各部委官网、政府法规数据库、法院官网、监管机构官网；A 级使用 OECD、UN、EU、World Bank。
- 金融/经济/股票：S 级优先中央银行、财政部、统计局、IMF、World Bank、OECD、SEC、公司 IR、年报、财报、SEC EDGAR；A 级使用 FRED、Trading Economics、Yahoo Finance、Bloomberg、Reuters。
- 公司/产品/开源项目：S 级优先公司官网、官方文档、官方公告、官方 GitHub/GitLab、README、Docs、Release Notes；A 级使用官方博客、status page、Issues、Discussions。
- 医学/健康：S 级优先 WHO、CDC、NIH、NHS、Mayo Clinic、PubMed；A 级使用 Cochrane Library、医学期刊。
- 教育/课程：S 级优先大学官网、课程页面、官方教材；A 级使用 MIT OCW、Stanford Online、Coursera 官方课程。
- 地理/旅行/天气/灾害：S 级优先政府网站、官方旅游局、交通官网、气象局、JMA、NOAA、政府灾害平台；A 级使用 Google Maps、NHK、当地政府公告。
- 统计数据：S 级优先政府统计局、World Bank、OECD、UN Data、IMF；A 级使用 Statista、Our World in Data。
- 问答/社区：S 级优先 Stack Overflow、Stack Exchange、GitHub Issues；A 级使用 Reddit、Hacker News、知乎。
- 错误排查：S 级优先官方文档、GitHub Issues、Stack Overflow；A 级使用官方论坛、Discord、邮件列表。

## 简化公式

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

## 判断标准

- 是否是一手来源；是否有明确作者或机构；是否有发布时间或版本号；是否可被其他来源验证；是否存在商业立场；是否适合当前用途；是否过时。
""".strip()


SOURCE_PRIORITY_SYSTEM_PROMPT = """
你是 KnowledgeForge QueryEngine 的查询队列规划助手。你只负责把待查询条目转成可执行的 JSON 查询队列。

必须遵守：
- 只输出 JSON object，不要输出 Markdown。
- 根据权威来源优先级表判断类别、查询目的和来源优先级。
- query_text 必须是短搜索词，格式优先为“领域名 + 知识点/证据主题”，不要写“补充”“查找”“关键依据”等操作性措辞。
- 对技术、政策、新闻、价格、版本、法规、漏洞等时效性强的条目，在 acceptance_criteria 中要求核对发布时间、版本号或发布日期。
- 输出任务必须适配 KnowledgeForge 当前 query task 字段。
""".strip()


SOURCE_PRIORITY_QUEUE_SCHEMA: dict[str, Any] = {
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
                }
            ],
            "authority_queries": ["带 site: 的权威查询词"],
            "acceptance_criteria": ["验收标准"],
            "status": "pending",
        }
    ]
}


TIME_SENSITIVE_TOKENS = (
    "最新",
    "新闻",
    "时事",
    "价格",
    "法规",
    "政策",
    "漏洞",
    "版本",
    "release",
    "changelog",
    "security",
    "cve",
    "kev",
    "today",
    "recent",
    "latest",
)


def build_source_priority_user_prompt(*, query_items: list[dict[str, Any]], domain: str) -> str:
    return "\n\n".join(
        [
            "请根据下面的权威来源优先级表，为待查询列表生成 JSON 查询队列。",
            f"领域名：{domain or '未指定'}",
            "权威来源优先级表：",
            SOURCE_PRIORITY_POLICY,
            "待查询列表 JSON：",
            json.dumps(query_items, ensure_ascii=False, indent=2),
            "输出 JSON schema 示例：",
            json.dumps(SOURCE_PRIORITY_QUEUE_SCHEMA, ensure_ascii=False, indent=2),
        ]
    )


def parse_source_priority_json_response(content: str) -> dict[str, Any]:
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


def normalize_source_priority_queue(payload: dict[str, Any], *, domain: str) -> list[dict[str, Any]]:
    raw_tasks = payload.get("tasks") or payload.get("queue") or payload.get("query_tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("LLM response must contain tasks, queue, or query_tasks as a list.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_tasks, start=1):
        if not isinstance(raw, dict):
            continue
        task = dict(raw)
        task_id = _dedupe_task_id(str(task.get("task_id", "")).strip() or f"source-priority-{index:03d}", seen_ids, index)
        query_text = _clean_text(task.get("query_text") or task.get("query") or task.get("title"))
        if domain and query_text and domain.lower() not in query_text.lower():
            query_text = f"{domain} {query_text}"
        claim = _clean_text(task.get("claim_or_gap") or query_text)
        expected = _string_list(task.get("expected_evidence"))
        preferred = _string_list(task.get("preferred_source_types") or task.get("source_priority"))
        advice = advise_source_priority(
            domain=domain,
            query=query_text or claim,
            claim=claim,
            expected_info=expected,
            source_priority=preferred,
            acceptance_criteria=_string_list(task.get("acceptance_criteria")),
        )
        normalized.append(
            {
                "task_id": task_id,
                "task_type": "query",
                "target_node_id": _clean_text(task.get("target_node_id") or task.get("item_id")),
                "section": _clean_text(task.get("section")) or "证据与来源",
                "claim_or_gap": claim,
                "query_text": query_text or claim,
                "expected_evidence": expected or advice["expected_evidence"],
                "preferred_source_types": advice["preferred_source_types"],
                "source_priority": task.get("source_priority", []),
                "authority_queries": _string_list(task.get("authority_queries")) or advice["authority_queries"],
                "acceptance_criteria": advice["acceptance_criteria"],
                "status": "pending",
            }
        )
    if not normalized:
        raise ValueError("No usable query tasks were returned by the LLM.")
    return normalized


def advise_source_priority(
    *,
    domain: str,
    query: str,
    claim: str = "",
    expected_info: list[str] | None = None,
    source_priority: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    max_domains: int = 3,
) -> dict[str, list[str]]:
    expected = _dedupe_terms(expected_info or [])
    preferred = _dedupe_terms([*(source_priority or []), *_infer_source_types(domain=domain, query=query, claim=claim, expected=expected)])
    if not preferred:
        preferred = ["official documentation", "wikipedia"]
    criteria = _dedupe_terms(acceptance_criteria or [])
    if not criteria:
        criteria = ["至少得到一条可访问链接", "来源能直接支撑 claim_or_gap"]
    if _is_time_sensitive(" ".join([query, claim, *expected, *preferred])):
        criteria = _dedupe_terms([*criteria, "核对发布时间、版本号或发布日期"])
    priority_domains = domains_for_source_priority(
        preferred,
        query=query,
        expected_info=expected,
        max_domains=max_domains,
    )
    authority_queries = build_site_constrained_queries(query, priority_domains, max_domains=max_domains)
    return {
        "preferred_source_types": preferred,
        "expected_evidence": expected or ["官方或高公信力来源", "与查询目标直接相关的说明"],
        "acceptance_criteria": criteria,
        "authority_queries": authority_queries,
        "priority_domains": priority_domains,
    }


def _infer_source_types(*, domain: str, query: str, claim: str, expected: list[str]) -> list[str]:
    text = " ".join([domain, query, claim, *expected]).lower()
    inferred: list[str] = []
    if any(token in text for token in ("定义", "边界", "概念", "overview", "definition", "通用")):
        inferred.extend(["official documentation", "wikipedia"])
    if any(token in text for token in ("python", "javascript", "typescript", "react", "vue", "node", "docker", "kubernetes", "api", "sdk", "github", "编程", "技术", "用法")):
        inferred.extend(["official documentation", "technical docs", "GitHub docs"])
    if any(token in text for token in ("ai", "ml", "machine learning", "deep learning", "llm", "模型", "论文", "paper", "benchmark", "transformer")):
        inferred.extend(["AI/ML paper", "academic", "model card"])
    if any(token in text for token in ("新闻", "时事", "趋势", "news", "recent", "latest")):
        inferred.extend(["news", "official announcement"])
    if any(token in text for token in ("漏洞", "cve", "security", "owasp", "nist", "安全")):
        inferred.extend(["security advisory", "CVE/NVD", "official documentation"])
    if any(token in text for token in ("政策", "法规", "法律", "监管", "law", "policy")):
        inferred.extend(["government source", "regulatory source"])
    if any(token in text for token in ("release", "changelog", "版本", "更新")):
        inferred.extend(["release notes", "official documentation", "GitHub releases"])
    return inferred


def _is_time_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in TIME_SENSITIVE_TOKENS)


def _dedupe_task_id(task_id: str, seen_ids: set[str], index: int) -> str:
    if task_id in seen_ids:
        task_id = f"{task_id}-{index:03d}"
    seen_ids.add(task_id)
    return task_id


def _dedupe_terms(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_text(item)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped


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
