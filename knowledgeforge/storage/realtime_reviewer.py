from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import yaml

from knowledgeforge.config import AppConfig
from knowledgeforge.models import RequestContext
from knowledgeforge.utils.paths import ensure_directory, sanitize_path_segment, slugify_filename
from knowledgeforge.utils.time import now_iso, today_compact


RealtimeReviewStatus = Literal["saved", "skipped", "failed"]


@dataclass(slots=True)
class RealtimeReviewCandidate:
    agent: str
    round_number: int
    plan_item_id: str
    query: str
    source_type: str
    documents: list[Any]
    context: RequestContext
    platform_type: str = ""


@dataclass(slots=True)
class RealtimeReviewResult:
    saved_paths: list[str] = field(default_factory=list)
    skipped_sources: list[dict[str, str]] = field(default_factory=list)
    failed_sources: list[dict[str, str]] = field(default_factory=list)
    index_path: str = ""
    status: RealtimeReviewStatus = "skipped"

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_paths": self.saved_paths,
            "skipped_sources": self.skipped_sources,
            "failed_sources": self.failed_sources,
            "index_path": self.index_path,
            "status": self.status,
        }


class RealtimeFileReviewer:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = Lock()

    def review_and_save(self, candidate: RealtimeReviewCandidate) -> RealtimeReviewResult:
        with self._lock:
            result = RealtimeReviewResult()
            context = candidate.context
            domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
            subdomain = context.subdomains[0] if context.subdomains else "通用"
            subdomain_dir = domain_dir / sanitize_path_segment(subdomain, "general")
            ensure_directory(subdomain_dir)

            existing_urls = self._existing_source_urls(domain_dir)
            accepted = []
            for document in candidate.documents:
                review_error = self._review_document(document, candidate)
                url = str(getattr(document, "url", "")).strip()
                if review_error:
                    result.skipped_sources.append({"url": url, "reason": review_error})
                    continue
                if url in existing_urls:
                    result.skipped_sources.append({"url": url, "reason": "duplicate_url"})
                    continue
                accepted.append(document)
                existing_urls.add(url)

            if accepted:
                path = self._write_plan_item_document(candidate, accepted, subdomain, subdomain_dir)
                result.saved_paths.append(path)

            result.index_path = self.refresh_domain_index(context)
            result.status = "saved" if result.saved_paths else "skipped"
            return result

    def refresh_domain_index(self, context: RequestContext) -> str:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        ensure_directory(domain_dir)
        readme_path = domain_dir / "README.md"
        readme_path.write_text(self.render_domain_index(context, domain_dir), encoding="utf-8")
        return readme_path.as_posix()

    @staticmethod
    def render_domain_index(context: RequestContext, domain_dir: Path) -> str:
        timestamp = now_iso()
        realtime_docs = RealtimeFileReviewer.scan_realtime_documents(domain_dir)
        sections = "\n".join(f"- {topic}" for topic in context.subdomains) or "- 通用"
        realtime_rows = [
            "| {path} | {agent} | {plan_item_id} | {source_count} | {updated_at} |".format(
                path=item["path"],
                agent=item["agent"],
                plan_item_id=item["plan_item_id"],
                source_count=item["source_count"],
                updated_at=item["updated_at"],
            )
            for item in realtime_docs
        ]
        return "\n".join(
            [
                f"# {context.domain}",
                "",
                "## 领域概览",
                "",
                f"当前领域目录用于保存 {context.domain} 的知识文档与索引信息。",
                f"已规划子主题：{', '.join(context.subdomains) if context.subdomains else '通用'}。",
                f"当前实时保存文档数量：{len(realtime_docs)}。",
                f"索引更新时间：{timestamp}。",
                "",
                "## 子主题",
                "",
                sections,
                "",
                "## 实时保存文档",
                "",
                "| 路径 | Agent | 计划项 | 来源数 | 更新时间 |",
                "|---|---|---|---|---|",
                *(realtime_rows or ["| 暂无 | - | - | 0 | - |"]),
                "",
            ]
        )

    @staticmethod
    def scan_realtime_documents(domain_dir: Path) -> list[dict[str, Any]]:
        if not domain_dir.exists():
            return []
        documents: list[dict[str, Any]] = []
        for path in sorted(domain_dir.glob("**/*.md")):
            if path.name == "README.md":
                continue
            front_matter = RealtimeFileReviewer._read_front_matter(path)
            if not front_matter.get("realtime_saved"):
                continue
            documents.append(
                {
                    "path": str(front_matter.get("path") or path.as_posix()),
                    "agent": str(front_matter.get("agent") or ""),
                    "plan_item_id": str(front_matter.get("plan_item_id") or ""),
                    "source_count": len(front_matter.get("sources") or []),
                    "updated_at": str(front_matter.get("updated_at") or ""),
                }
            )
        return documents

    def _write_plan_item_document(
        self,
        candidate: RealtimeReviewCandidate,
        documents: list[Any],
        subdomain: str,
        subdomain_dir: Path,
    ) -> str:
        timestamp = now_iso()
        context = candidate.context
        document_id = f"realtime-{uuid.uuid4().hex[:12]}"
        title = f"{context.domain} {candidate.agent} {candidate.plan_item_id} 实时资料"
        suffix = "media" if candidate.agent == "MediaEngine" else "query"
        filename = f"{today_compact()}-{slugify_filename(title, document_id)}-{suffix}.md"
        document_path = subdomain_dir / filename
        relative_path = document_path.as_posix()
        doc_type = "trend" if candidate.agent == "MediaEngine" else "source"
        front_matter = {
            "id": document_id,
            "title": title,
            "domain": context.domain,
            "subdomain": subdomain,
            "doc_type": doc_type,
            "source_type": suffix,
            "agent": candidate.agent,
            "round": candidate.round_number,
            "status": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "version": "v1",
            "path": relative_path,
            "tags": [*context.focus_points, "realtime", candidate.plan_item_id],
            "realtime_saved": True,
            "plan_item_id": candidate.plan_item_id,
            "query": candidate.query,
            "platform_type": candidate.platform_type,
            "sources": [
                {
                    "title": str(getattr(document, "title", "")).strip(),
                    "url": str(getattr(document, "url", "")).strip(),
                    "publisher": str(getattr(document, "publisher", "")).strip() or "unknown",
                    "retrieved_at": timestamp,
                    "reliability": self._reliability(candidate, document),
                }
                for document in documents
            ],
        }
        document_path.write_text(
            self._render_document(front_matter, title, candidate, documents, timestamp),
            encoding="utf-8",
        )
        return relative_path

    def _render_document(
        self,
        front_matter: dict[str, Any],
        title: str,
        candidate: RealtimeReviewCandidate,
        documents: list[Any],
        timestamp: str,
    ) -> str:
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        key_points = [
            f"{candidate.agent} 在计划项 {candidate.plan_item_id} 中获取到 {len(documents)} 个合格来源。",
            f"本文件按计划项实时保存，原始查询为：{candidate.query}",
            "内容仍为 draft，需等待后续完整性评估、结构化治理和质量检测。",
        ]
        source_rows = []
        body_sections = []
        entity_rows = [f"| {candidate.context.domain} | Domain | 目标领域 | S1 |"]
        relation_rows = []
        for index, document in enumerate(documents, start=1):
            title_text = str(getattr(document, "title", "")).strip()
            url = str(getattr(document, "url", "")).strip()
            snippet = str(getattr(document, "snippet", "")).strip()
            content = str(getattr(document, "content", "")).strip()
            source_label = f"S{index}"
            source_rows.append(
                f"| {source_label} | {title_text} | {self._table_text(snippet or content[:160])} | {front_matter['sources'][index - 1]['reliability']} | {url} |"
            )
            body_sections.append(
                "\n".join(
                    [
                        f"### {title_text}",
                        "",
                        f"来源：{url}",
                        "",
                        snippet or "暂无摘要。",
                        "",
                        "#### 原始材料摘录",
                        "",
                        self._excerpt(content or snippet),
                    ]
                )
            )
            entity_rows.append(f"| {title_text} | Source | 实时保存来源 | {source_label} |")
            relation_rows.append(f"| {candidate.context.domain} | has_realtime_source | {title_text} | {source_label} |")

        return "\n".join(
            [
                "---",
                front_matter_text,
                "---",
                "",
                f"# {title}",
                "",
                "## 摘要",
                "",
                f"本文档实时保存 {candidate.context.domain} 在 {candidate.agent} 计划项 {candidate.plan_item_id} 中获取并通过基础审查的资料。",
                "它保留来源链接、查询语句、Agent、轮次和本地路径，用于后续补检索决策、完整性评估和质量闭环。",
                "",
                "## 关键结论",
                "",
                *[f"- {item}" for item in key_points],
                "",
                "## 背景与上下文",
                "",
                f"领域：{candidate.context.domain}",
                f"子领域：{', '.join(candidate.context.subdomains) if candidate.context.subdomains else '通用'}",
                f"计划项：{candidate.plan_item_id}",
                f"查询：{candidate.query}",
                f"来源类型：{candidate.source_type}",
                f"平台类型：{candidate.platform_type or '无'}",
                f"保存时间：{timestamp}",
                "",
                "## 正文",
                "",
                "\n\n".join(body_sections),
                "",
                "## 证据与来源",
                "",
                "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |",
                "|---|---|---|---|---|",
                *source_rows,
                "",
                "## 实体与关系候选",
                "",
                "### 实体候选",
                "",
                "| 实体 | 类型 | 描述 | 来源 |",
                "|---|---|---|---|",
                *entity_rows,
                "",
                "### 关系候选",
                "",
                "| 主体 | 关系 | 客体 | 来源 |",
                "|---|---|---|---|",
                *relation_rows,
                "",
                "## 冲突与不确定性",
                "",
                "- 实时保存内容尚未经过完整治理质检。",
                "",
                "## 后续动作",
                "",
                "- 在最终综合文档与质量检测阶段复核这些来源是否足以支撑知识沉淀。",
                "",
                "## 变更记录",
                "",
                "| 版本 | 时间 | 变更说明 |",
                "|---|---|---|",
                f"| v1 | {timestamp[:10]} | 实时保存计划项资料 |",
                "",
            ]
        )

    @staticmethod
    def _review_document(document: Any, candidate: RealtimeReviewCandidate) -> str:
        if not str(getattr(document, "url", "")).strip():
            return "missing_url"
        if not str(getattr(document, "title", "")).strip():
            return "missing_title"
        if not (str(getattr(document, "content", "")).strip() or str(getattr(document, "snippet", "")).strip()):
            return "missing_content"
        if float(getattr(document, "score", 0) or 0) <= 0:
            return "invalid_score"
        if candidate.agent not in {"QueryEngine", "MediaEngine"}:
            return "unsupported_agent"
        if candidate.agent == "QueryEngine" and candidate.source_type not in {"official", "tutorial", "query_plan", "reference"}:
            return "unsupported_source_type"
        if candidate.agent == "MediaEngine" and candidate.source_type not in {"social", "community", "blog", "media"}:
            return "unsupported_source_type"
        return ""

    @staticmethod
    def _existing_source_urls(domain_dir: Path) -> set[str]:
        urls: set[str] = set()
        if not domain_dir.exists():
            return urls
        for path in domain_dir.glob("**/*.md"):
            front_matter = RealtimeFileReviewer._read_front_matter(path)
            for source in front_matter.get("sources") or []:
                if isinstance(source, dict) and source.get("url"):
                    urls.add(str(source["url"]))
        return urls

    @staticmethod
    def _read_front_matter(path: Path) -> dict[str, Any]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        if not content.startswith("---\n"):
            return {}
        end = content.find("\n---", 4)
        if end == -1:
            return {}
        try:
            payload = yaml.safe_load(content[4:end]) or {}
        except yaml.YAMLError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _reliability(candidate: RealtimeReviewCandidate, document: Any) -> str:
        if candidate.agent == "QueryEngine" and getattr(document, "source_type", "") == "official":
            return "high"
        if candidate.agent == "MediaEngine" and getattr(document, "platform_type", "") in {"community", "blog"}:
            return "medium"
        if candidate.agent == "MediaEngine":
            return "low"
        return "medium"

    @staticmethod
    def _excerpt(value: str, limit: int = 1200) -> str:
        text = " ".join(value.split())
        return text[:limit] or "暂无。"

    @staticmethod
    def _table_text(value: str) -> str:
        return " ".join(value.split()).replace("|", "\\|")[:220]
