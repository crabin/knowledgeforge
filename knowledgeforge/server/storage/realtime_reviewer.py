from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import yaml

from knowledgeforge.server.config import AppConfig
from knowledgeforge.server.models import RequestContext
from knowledgeforge.server.utils.knowledge_tree import module_directory, module_labels_by_id, plan_path_for_role
from knowledgeforge.server.utils.paths import ensure_directory, sanitize_path_segment, slugify_filename
from knowledgeforge.server.utils.time import now_iso, today_compact


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
    subdomain: str = ""
    doc_type: str = "source"
    module_id: str = ""
    module_label: str = ""
    doc_role: str = "topic_article"
    planned_path: str = ""
    article_title: str = ""
    url: str = ""


@dataclass(slots=True)
class RealtimeReviewResult:
    saved_paths: list[str] = field(default_factory=list)
    skipped_sources: list[dict[str, str]] = field(default_factory=list)
    failed_sources: list[dict[str, str]] = field(default_factory=list)
    index_path: str = ""
    subdomain_index_path: str = ""
    module_index_path: str = ""
    module_overview_path: str = ""
    index_paths: list[str] = field(default_factory=list)
    status: RealtimeReviewStatus = "skipped"

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_paths": self.saved_paths,
            "skipped_sources": self.skipped_sources,
            "failed_sources": self.failed_sources,
            "index_path": self.index_path,
            "subdomain_index_path": self.subdomain_index_path,
            "index_paths": self.index_paths,
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
            subdomain = candidate.subdomain or (context.core_topics[0] if context.core_topics else "通用")
            module_id = candidate.module_id or "core_topics"
            module_label = candidate.module_label or module_labels_by_id().get(module_id, "Core Topics")
            target_dir = Path(
                candidate.planned_path
            ).parent if candidate.planned_path else self._default_target_dir(domain_dir, module_id, subdomain)
            ensure_directory(target_dir)

            existing_urls = self._existing_source_urls(domain_dir)
            for document in candidate.documents:
                review_error = self._review_document(document, candidate)
                url = str(getattr(document, "url", "")).strip()
                if review_error:
                    result.skipped_sources.append({"url": url, "reason": review_error})
                    continue
                if url in existing_urls:
                    result.skipped_sources.append({"url": url, "reason": "duplicate_url"})
                    continue
                path = self._write_article_document(candidate, document, subdomain, target_dir)
                result.saved_paths.append(path)
                existing_urls.add(url)

            result.index_path = self.refresh_domain_index(context)
            result.module_overview_path = self.refresh_module_overview(context, module_id)
            result.module_index_path = self.refresh_module_index(context, module_id)
            result.subdomain_index_path = self.refresh_subdomain_index(context, subdomain)
            result.index_paths = [
                path
                for path in [
                    result.index_path,
                    result.module_overview_path,
                    result.module_index_path,
                    result.subdomain_index_path,
                ]
                if path
            ]
            result.status = "saved" if result.saved_paths else "skipped"
            return result

    def refresh_domain_index(self, context: RequestContext) -> str:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        ensure_directory(domain_dir)
        readme_path = domain_dir / "README.md"
        readme_path.write_text(self.render_domain_index(context, domain_dir), encoding="utf-8")
        (domain_dir / "index.md").write_text(self.render_domain_navigation(context, domain_dir), encoding="utf-8")
        return readme_path.as_posix()

    def refresh_module_overview(self, context: RequestContext, module_id: str) -> str:
        module_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain") / module_directory(module_id)
        ensure_directory(module_dir)
        readme_path = module_dir / "README.md"
        readme_path.write_text(self.render_module_overview(context, module_id, module_dir), encoding="utf-8")
        return readme_path.as_posix()

    def refresh_module_index(self, context: RequestContext, module_id: str) -> str:
        module_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain") / module_directory(module_id)
        ensure_directory(module_dir)
        index_path = module_dir / "index.md"
        index_path.write_text(self.render_module_index(context, module_id, module_dir), encoding="utf-8")
        return index_path.as_posix()

    def refresh_subdomain_index(self, context: RequestContext, subdomain: str) -> str:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        subdomain_dir = domain_dir / "02_core_topics" / sanitize_path_segment(subdomain, "general")
        ensure_directory(subdomain_dir)
        readme_path = subdomain_dir / "README.md"
        index_path = subdomain_dir / "index.md"
        readme_path.write_text(self.render_subdomain_overview(context, subdomain_dir, subdomain), encoding="utf-8")
        index_path.write_text(self.render_subdomain_index(context, subdomain_dir, subdomain), encoding="utf-8")
        return index_path.as_posix()

    @staticmethod
    def render_domain_index(context: RequestContext, domain_dir: Path) -> str:
        timestamp = now_iso()
        realtime_docs = RealtimeFileReviewer.scan_realtime_documents(domain_dir)
        subdomain_rows = []
        subdomains = sorted({item["subdomain"] for item in realtime_docs if item.get("subdomain")}) or context.core_topics or ["通用"]
        for topic in subdomains:
            topic_segment = sanitize_path_segment(topic, "general")
            subdomain_rows.append(f"| {topic} | 02_core_topics/{topic_segment}/README.md |")
        realtime_rows = [
            "| {path} | {module_label} | {subdomain} | {agent} | {plan_item_id} | {url} | {updated_at} |".format(
                path=item["path"],
                module_label=item.get("module_label", ""),
                subdomain=item["subdomain"],
                agent=item["agent"],
                plan_item_id=item["plan_item_id"],
                url=item["url"],
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
                f"已规划模块：{', '.join(item['directory'] for item in context.knowledge_modules) if context.knowledge_modules else '默认模块'}。",
                f"已规划核心主题：{', '.join(context.core_topics) if context.core_topics else '通用'}。",
                f"当前实时保存文档数量：{len(realtime_docs)}。",
                f"索引更新时间：{timestamp}。",
                "",
                "## 子主题",
                "",
                "| 子领域 | 索引 |",
                "|---|---|",
                *(subdomain_rows or ["| 通用 | 通用/README.md |"]),
                "",
                "## 实时保存文档",
                "",
                "| 路径 | 模块 | 子领域 | Agent | 计划项 | URL | 更新时间 |",
                "|---|---|---|---|---|---|---|",
                *(realtime_rows or ["| 暂无 | - | - | - | - | - | - |"]),
                "",
            ]
        )

    @staticmethod
    def render_domain_navigation(context: RequestContext, domain_dir: Path) -> str:
        rows = [
            f"| {item['label']} | {item['directory']}/README.md | {item['priority']} |"
            for item in context.knowledge_modules
        ]
        topic_rows = [
            f"| {topic} | 02_core_topics/{sanitize_path_segment(topic, 'topic')}/README.md |"
            for topic in (context.core_topics or context.subdomains or ["通用"])
        ]
        return "\n".join(
            [
                f"# Knowledge Index: {context.domain}",
                "",
                "## 1. Knowledge Map",
                "",
                f"本知识库用于系统整理和学习 {context.domain} 的核心知识模块与主题分支。",
                "",
                "## 2. Learning Structure",
                "",
                "| Module | Path | Priority |",
                "|---|---|---|",
                *(rows or ["| Overview | 00_overview/README.md | high |"]),
                "",
                "## 3. Core Topics",
                "",
                "| Topic | Path |",
                "|---|---|",
                *(topic_rows or ["| 通用 | 02_core_topics/general/README.md |"]),
                "",
            ]
        )

    @staticmethod
    def render_module_overview(context: RequestContext, module_id: str, module_dir: Path) -> str:
        module_label = module_labels_by_id().get(module_id, module_id)
        docs = [item for item in RealtimeFileReviewer.scan_realtime_documents(module_dir) if item.get("module_id") == module_id]
        return "\n".join(
            [
                f"# {context.domain} / {module_label}",
                "",
                "## 模块概览",
                "",
                f"该模块承载 {context.domain} 的 {module_label} 相关知识。",
                f"当前实时文档数量：{len(docs)}。",
                "",
            ]
        )

    @staticmethod
    def render_module_index(context: RequestContext, module_id: str, module_dir: Path) -> str:
        module_label = module_labels_by_id().get(module_id, module_id)
        docs = [item for item in RealtimeFileReviewer.scan_realtime_documents(module_dir) if item.get("module_id") == module_id]
        rows = [
            f"| {item['title']} | {item['path']} | {item['doc_role']} | {item['status']} |"
            for item in docs
        ]
        return "\n".join(
            [
                f"# Index: {context.domain} / {module_label}",
                "",
                "## 模块文档",
                "",
                "| 标题 | 路径 | 文档角色 | 状态 |",
                "|---|---|---|---|",
                *(rows or ["| 暂无 | - | - | - |"]),
                "",
            ]
        )

    @staticmethod
    def render_subdomain_overview(context: RequestContext, subdomain_dir: Path, subdomain: str) -> str:
        timestamp = now_iso()
        realtime_docs = [
            item for item in RealtimeFileReviewer.scan_realtime_documents(subdomain_dir) if item.get("subdomain") == subdomain
        ]
        return "\n".join(
            [
                f"# {subdomain} Overview",
                "",
                "## 子领域概览",
                "",
                f"当前子领域用于保存 {subdomain} 的文章级知识文档。",
                f"文章数量：{len(realtime_docs)}。",
                f"索引更新时间：{timestamp}。",
                "",
            ]
        )

    @staticmethod
    def render_subdomain_index(context: RequestContext, subdomain_dir: Path, subdomain: str) -> str:
        timestamp = now_iso()
        realtime_docs = [
            item for item in RealtimeFileReviewer.scan_realtime_documents(subdomain_dir) if item.get("subdomain") == subdomain
        ]
        rows = [
            "| {title} | {path} | {doc_role} | {source_type} | {status} | {plan_item_id} | {url} | {updated_at} |".format(
                title=item["title"],
                path=item["path"],
                doc_role=item.get("doc_role", ""),
                source_type=item["source_type"],
                status=item["status"],
                plan_item_id=item["plan_item_id"],
                url=item["url"],
                updated_at=item["updated_at"],
            )
            for item in realtime_docs
        ]
        return "\n".join(
            [
                f"# Index: {subdomain}",
                "",
                "## 文章列表",
                "",
                f"当前子领域用于保存 {subdomain} 的文章级知识文档。索引更新时间：{timestamp}。",
                "",
                "| 标题 | 路径 | 文档角色 | 来源类型 | 状态 | 计划项 | URL | 更新时间 |",
                "|---|---|---|---|---|---|---|---|",
                *(rows or ["| 暂无 | - | - | - | - | - | - | - |"]),
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
                    "title": str(front_matter.get("title") or path.stem),
                    "agent": str(front_matter.get("agent") or ""),
                    "plan_item_id": str(front_matter.get("plan_item_id") or ""),
                    "subdomain": str(front_matter.get("subdomain") or ""),
                    "source_count": len(front_matter.get("sources") or []),
                    "source_type": str(front_matter.get("source_type") or ""),
                    "doc_role": str(front_matter.get("doc_role") or ""),
                    "module_id": str(front_matter.get("module_id") or ""),
                    "module_label": str(front_matter.get("module_label") or ""),
                    "status": str(front_matter.get("status") or ""),
                    "updated_at": str(front_matter.get("updated_at") or ""),
                    "url": str(front_matter.get("url") or ""),
                }
            )
        return documents

    def _write_article_document(
        self,
        candidate: RealtimeReviewCandidate,
        document: Any,
        subdomain: str,
        subdomain_dir: Path,
    ) -> str:
        timestamp = now_iso()
        context = candidate.context
        document_id = f"realtime-{uuid.uuid4().hex[:12]}"
        title = candidate.article_title or str(getattr(document, "title", "")).strip() or f"{context.domain} 资料"
        suffix = "media" if candidate.agent == "MediaEngine" else "query"
        planned_path = Path(candidate.planned_path) if candidate.planned_path else None
        if planned_path and planned_path.suffix == ".md" and planned_path.name.lower() not in {"readme.md", "index.md"}:
            document_path = planned_path
        else:
            filename = f"{today_compact()}-{slugify_filename(title, document_id)}-{suffix}.md"
            document_path = subdomain_dir / filename
        relative_path = document_path.as_posix()
        doc_type = candidate.doc_type or ("trend" if candidate.agent == "MediaEngine" else "source")
        document_url = str(getattr(document, "url", "")).strip()
        front_matter = {
            "id": document_id,
            "title": title,
            "domain": context.domain,
            "subdomain": subdomain,
            "doc_type": doc_type,
            "source_type": suffix,
            "doc_role": candidate.doc_role,
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
            "module_id": candidate.module_id or "core_topics",
            "module_label": candidate.module_label or module_labels_by_id().get(candidate.module_id or "core_topics", "Core Topics"),
            "query": candidate.query,
            "platform_type": candidate.platform_type,
            "url": document_url,
            "planned_path": candidate.planned_path or relative_path,
            "sources": [
                {
                    "title": str(getattr(document, "title", "")).strip(),
                    "url": document_url,
                    "publisher": str(getattr(document, "publisher", "")).strip() or "unknown",
                    "retrieved_at": timestamp,
                    "reliability": self._reliability(candidate, document),
                }
            ],
        }
        document_path.write_text(
            self._render_document(front_matter, title, candidate, document, timestamp),
            encoding="utf-8",
        )
        return relative_path

    def _render_document(
        self,
        front_matter: dict[str, Any],
        title: str,
        candidate: RealtimeReviewCandidate,
        document: Any,
        timestamp: str,
    ) -> str:
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        key_points = [
            f"{candidate.agent} 在计划项 {candidate.plan_item_id} 中抓取并保存了 1 篇文章级资料。",
            f"本文件按单链接实时保存，原始查询为：{candidate.query}",
            "内容仍为 draft，需等待后续完整性评估、结构化治理和质量检测。",
        ]
        title_text = str(getattr(document, "title", "")).strip()
        url = str(getattr(document, "url", "")).strip()
        snippet = str(getattr(document, "snippet", "")).strip()
        content = str(getattr(document, "content", "")).strip()
        source_rows = [
            f"| S1 | {title_text} | {self._table_text(snippet or content[:160])} | {front_matter['sources'][0]['reliability']} | {url} |"
        ]
        body_sections = [
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
        ]
        entity_rows = [f"| {candidate.context.domain} | Domain | 目标领域 | S1 |"]
        entity_rows.append(f"| {title_text} | Source | 实时保存来源 | S1 |")
        relation_rows = [f"| {candidate.context.domain} | has_realtime_source | {title_text} | S1 |"]

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
                f"子领域：{candidate.subdomain or (candidate.context.subdomains[0] if candidate.context.subdomains else '通用')}",
                f"模块：{candidate.module_label or module_labels_by_id().get(candidate.module_id or 'core_topics', 'Core Topics')}",
                f"文档角色：{candidate.doc_role}",
                f"计划项：{candidate.plan_item_id}",
                f"查询：{candidate.query}",
                f"来源类型：{candidate.source_type}",
                f"平台类型：{candidate.platform_type or '无'}",
                f"目标链接：{candidate.url or url}",
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
    def _default_target_dir(domain_dir: Path, module_id: str, subdomain: str) -> Path:
        base = domain_dir / module_directory(module_id)
        if module_id == "core_topics" or subdomain:
            return base / sanitize_path_segment(subdomain or "general", "general")
        return base

    @staticmethod
    def _excerpt(value: str, limit: int = 1200) -> str:
        text = " ".join(value.split())
        return text[:limit] or "暂无。"

    @staticmethod
    def _table_text(value: str) -> str:
        return " ".join(value.split()).replace("|", "\\|")[:220]
