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
        query_plan_path = self._write_query_plan_document(
            context=context,
            query_output=outputs.get("QueryEngine"),
            subdomain=subdomain,
            subdomain_dir=subdomain_dir,
            round_number=round_number,
        )
        if query_plan_path:
            document_body = document_body.replace(
                "## 后续动作\n\n",
                f"## 后续动作\n\n- QueryEngine 查询计划已保存：{query_plan_path}\n",
                1,
            )

        ensure_directory(domain_dir)
        (domain_dir / "README.md").write_text(domain_readme, encoding="utf-8")
        document_path.write_text(document_body, encoding="utf-8")
        return artifact

    def _write_query_plan_document(
        self,
        *,
        context: RequestContext,
        query_output: EngineRunResult | None,
        subdomain: str,
        subdomain_dir: Path,
        round_number: int,
    ) -> str | None:
        if query_output is None:
            return None
        query_plan_lines = self._extract_query_plan_lines(query_output.raw_material)
        execution_events = [
            entry
            for entry in query_output.execution_log
            if str(entry.get("event", "")).startswith("query_")
        ]
        if not query_plan_lines and not execution_events:
            return None

        timestamp = now_iso()
        document_id = f"query-plan-{uuid.uuid4().hex[:12]}"
        title = f"{context.domain} QueryEngine 查询计划"
        filename = f"{today_compact()}-{slugify_filename(title, document_id)}-query.md"
        document_path = subdomain_dir / filename
        relative_path = document_path.as_posix()
        front_matter = {
            "id": document_id,
            "title": title,
            "domain": context.domain,
            "subdomain": subdomain,
            "doc_type": "note",
            "source_type": "query",
            "agent": "QueryEngine",
            "round": round_number,
            "status": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "version": "v1",
            "path": relative_path,
            "tags": [*context.focus_points, "query-plan"],
            "sources": [
                {
                    "title": "QueryEngine execution log",
                    "url": "local://query-engine/execution-log",
                    "publisher": "KnowledgeForge",
                    "retrieved_at": timestamp,
                    "reliability": "unknown",
                }
            ],
        }
        body = self._render_query_plan_document(
            front_matter=front_matter,
            title=title,
            context=context,
            query_plan_lines=query_plan_lines,
            execution_events=execution_events,
            timestamp=timestamp,
        )
        document_path.write_text(body, encoding="utf-8")
        return relative_path

    @staticmethod
    def _extract_query_plan_lines(raw_material: list[str]) -> list[str]:
        if "查询计划：" not in raw_material:
            return []
        start = raw_material.index("查询计划：") + 1
        lines: list[str] = []
        for item in raw_material[start:]:
            if item in {"反思结论：", "官方文档优先：", "教程/补充资料："} or item.startswith("反思结论："):
                break
            if item.startswith("- Q") or item.startswith("- ☑") or item.startswith("- ☐") or item.startswith("  "):
                lines.append(item)
        return lines

    @staticmethod
    def _render_query_plan_document(
        *,
        front_matter: dict,
        title: str,
        context: RequestContext,
        query_plan_lines: list[str],
        execution_events: list[dict],
        timestamp: str,
    ) -> str:
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        event_rows = []
        for index, entry in enumerate(execution_events, start=1):
            details = entry.get("details", {})
            event_rows.append(
                "| E{index} | {event} | {node} | {query} | {status} |".format(
                    index=index,
                    event=entry.get("event", ""),
                    node=entry.get("node", ""),
                    query=str(details.get("query", details.get("question", ""))).replace("|", "\\|"),
                    status=details.get("status", ""),
                )
            )
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
                f"本文档保存 {context.domain} / {', '.join(context.subdomains)} 在本轮 QueryEngine 执行前生成的查询计划、预期信息和执行状态。",
                "它用于审计查询决策，不等同于已验证知识结论。",
                "",
                "## 关键结论",
                "",
                "- QueryEngine 已在检索前生成结构化查询计划。",
                "- 每个查询问题保留 Google 风格查询语句、预期信息、满足标准和补查查询。",
                "- 执行事件可用于判断哪些问题已满足、哪些仍需补检索。",
                "",
                "## 背景与上下文",
                "",
                f"领域：{context.domain}",
                f"子领域：{', '.join(context.subdomains)}",
                f"时间范围：{context.time_window}",
                f"生成时间：{timestamp}",
                "",
                "## 正文",
                "",
                "### 查询计划",
                "",
                *(query_plan_lines or ["- 暂无结构化查询计划。"]),
                "",
                "### 执行事件",
                "",
                "| 编号 | 事件 | 节点 | 查询或问题 | 状态 |",
                "|---|---|---|---|---|",
                *(event_rows or ["| E1 | none | QueryEngine | 暂无执行事件 | unknown |"]),
                "",
                "## 证据与来源",
                "",
                "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |",
                "|---|---|---|---|---|",
                "| S1 | QueryEngine execution log | 查询计划与执行事件 | unknown | 本地执行日志 |",
                "",
                "## 实体与关系候选",
                "",
                "### 实体候选",
                "",
                "| 实体 | 类型 | 描述 | 来源 |",
                "|---|---|---|---|",
                f"| {context.domain} | Domain | 目标领域 | S1 |",
                "",
                "### 关系候选",
                "",
                "| 主体 | 关系 | 客体 | 来源 |",
                "|---|---|---|---|",
                f"| QueryEngine | planned_query_for | {context.domain} | S1 |",
                "",
                "## 冲突与不确定性",
                "",
                "- 查询计划只代表检索决策，不能替代已验证事实。",
                "",
                "## 后续动作",
                "",
                "- 对 status=insufficient 的查询问题执行补检索或人工复核。",
                "",
                "## 变更记录",
                "",
                "| 版本 | 时间 | 变更说明 |",
                "|---|---|---|",
                f"| v1 | {timestamp[:10]} | 初始创建 |",
                "",
            ]
        )

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
            raw_material = "\n".join(f"- {item}" for item in self._readable_raw_material(agent_name, output.raw_material))
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
    def _readable_raw_material(agent_name: str, raw_material: list[str]) -> list[str]:
        if agent_name != "QueryEngine":
            return raw_material
        readable: list[str] = []
        skipping_query_plan = False
        skipped_plan_lines = 0
        for item in raw_material:
            if item == "查询计划：":
                skipping_query_plan = True
                continue
            if skipping_query_plan:
                if item.startswith("反思结论："):
                    readable.append(f"查询计划明细已保存到独立 query 文档，本节省略 {skipped_plan_lines} 行执行清单。")
                    readable.append(item)
                    skipping_query_plan = False
                    continue
                skipped_plan_lines += 1
                continue
            readable.append(item)
        if skipping_query_plan:
            readable.append(f"查询计划明细已保存到独立 query 文档，本节省略 {skipped_plan_lines} 行执行清单。")
        return readable

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
