from __future__ import annotations

import uuid
from pathlib import Path

import yaml

from knowledgeforge.config import AppConfig
from knowledgeforge.models import (
    CompletenessResult,
    DocumentArtifact,
    EngineRunResult,
    RequestContext,
)
from knowledgeforge.utils.paths import ensure_directory, sanitize_path_segment, slugify_filename
from knowledgeforge.utils.time import now_iso, today_compact


class MarkdownKnowledgeWriter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def write(
        self,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
        completeness: CompletenessResult,
        round_number: int,
    ) -> DocumentArtifact:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        subdomain = context.subdomains[0] if context.subdomains else "通用"
        subdomain_dir = domain_dir / sanitize_path_segment(subdomain, "general")
        ensure_directory(subdomain_dir)

        document_id = f"article-{uuid.uuid4().hex[:12]}"
        title = f"{context.domain}知识综述"
        file_slug = slugify_filename(title, document_id)
        filename = f"{today_compact()}-{file_slug}-mixed.md"
        document_path = subdomain_dir / filename
        relative_path = document_path.as_posix()

        artifact = DocumentArtifact(
            document_id=document_id,
            title=title,
            domain=context.domain,
            subdomain=subdomain,
            path=relative_path,
            status="draft",
            version="v1",
        )

        document_body = self._render_document(artifact, context, outputs, completeness, round_number)
        domain_readme = self._render_domain_readme(context, outputs)

        ensure_directory(domain_dir)
        (domain_dir / "README.md").write_text(domain_readme, encoding="utf-8")
        document_path.write_text(document_body, encoding="utf-8")
        return artifact

    def _render_document(
        self,
        artifact: DocumentArtifact,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
        completeness: CompletenessResult,
        round_number: int,
    ) -> str:
        timestamp = now_iso()
        sources = [
            {
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "retrieved_at": source.retrieved_at,
                "reliability": source.reliability,
            }
            for output in outputs.values()
            for source in output.sources
        ]
        front_matter = {
            "id": artifact.document_id,
            "title": artifact.title,
            "domain": artifact.domain,
            "subdomain": artifact.subdomain,
            "doc_type": "article",
            "source_type": "mixed",
            "agent": "orchestrator",
            "round": round_number,
            "status": artifact.status,
            "created_at": timestamp,
            "updated_at": timestamp,
            "version": artifact.version,
            "path": artifact.path,
            "tags": context.focus_points,
            "sources": sources,
        }

        summary_lines = [
            f"本文围绕 {context.domain} 生成首版知识综述，覆盖 {', '.join(context.subdomains)}。",
            "当前版本由 Insight、Query、Media 三路并行采集结果汇总而成。",
            "文档保留了来源信息、候选实体关系、冲突与后续动作，供后续结构化抽取与质量检测使用。",
        ]

        if completeness.status == "pass":
            key_conclusions = [
                f"{context.domain} 已覆盖核心子主题，可以进入治理流程。",
                "来源包含可引用权威证据，满足知识沉淀最小条件。",
                "后续可在质量闭环阶段继续细化实体、关系与冲突裁决。",
            ]
        else:
            failure_hints = "、".join(completeness.failure_categories) if completeness.failure_categories else "来源不足"
            key_conclusions = [
                f"{context.domain} 当前结果为草稿状态，尚不满足入库条件（{failure_hints}）。",
                "需要执行补检索任务，补充权威来源后重新评估。",
                "在来源质量通过前，不允许冻结或进入报告流程。",
            ]

        body_sections = []
        for agent_name, output in outputs.items():
            bullet_points = "\n".join(f"- {point}" for point in output.key_points)
            raw_material = "\n".join(f"- {item}" for item in output.raw_material)
            body_sections.append(
                "\n".join(
                    [
                        f"### {agent_name}",
                        output.summary,
                        "",
                        "#### 关键信息",
                        bullet_points,
                        "",
                        "#### 原始材料摘录",
                        raw_material,
                    ]
                )
            )

        evidence_rows = []
        source_counter = 1
        for output in outputs.values():
            for source in output.sources:
                key_info = source.snippet if source.snippet.strip() else output.summary
                evidence_rows.append(
                    f"| S{source_counter} | {source.title} | {key_info} | {source.reliability} | {source.agent} |"
                )
                source_counter += 1

        relation_rows = []
        for subdomain in context.subdomains:
            relation_rows.append(f"| {context.domain} | covers | {subdomain} | S1 |")

        front_matter_text = yaml.safe_dump(
            front_matter,
            allow_unicode=True,
            sort_keys=False,
        ).strip()

        return "\n".join(
            [
                "---",
                front_matter_text,
                "---",
                "",
                f"# {artifact.title}",
                "",
                "## 摘要",
                "",
                "\n".join(summary_lines),
                "",
                "## 关键结论",
                "",
                "\n".join(f"- {item}" for item in key_conclusions),
                "",
                "## 背景与上下文",
                "",
                f"领域：{context.domain}",
                f"时间范围：{context.time_window}",
                f"关注点：{', '.join(context.focus_points)}",
                "",
                "## 正文",
                "",
                "\n\n".join(body_sections),
                "",
                "## 证据与来源",
                "",
                "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |",
                "|---|---|---|---|---|",
                *evidence_rows,
                "",
                "## 实体与关系候选",
                "",
                "### 实体候选",
                "",
                "| 实体 | 类型 | 描述 | 来源 |",
                "|---|---|---|---|",
                f"| {context.domain} | Domain | 目标领域 | S1 |",
                *[
                    f"| {subdomain} | SubTopic | 领域子主题 | S1 |"
                    for subdomain in context.subdomains
                ],
                "",
                "### 关系候选",
                "",
                "| 主体 | 关系 | 客体 | 来源 |",
                "|---|---|---|---|",
                *relation_rows,
                "",
                "## 冲突与不确定性",
                "",
                "- 暂无。",
                "",
                "## 后续动作",
                "",
                *(
                    [f"- {query}" for query in completeness.supplement_queries]
                    if completeness.supplement_queries
                    else ["- 暂无。"]
                ),
                "",
                "## 变更记录",
                "",
                "| 版本 | 时间 | 变更说明 |",
                "|---|---|---|",
                f"| {artifact.version} | {timestamp[:10]} | 初始创建 |",
                "",
            ]
        )

    @staticmethod
    def _render_domain_readme(
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
    ) -> str:
        sections = "\n".join(f"- {topic}" for topic in context.subdomains)
        sources = sum(len(output.sources) for output in outputs.values())
        return "\n".join(
            [
                f"# {context.domain}",
                "",
                "## 领域概览",
                "",
                f"当前领域目录用于保存 {context.domain} 的知识文档与索引信息。",
                f"已规划子主题：{', '.join(context.subdomains)}。",
                f"当前批次已汇总来源数量：{sources}。",
                "",
                "## 子主题",
                "",
                sections,
                "",
            ]
        )
