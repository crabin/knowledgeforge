from __future__ import annotations

import uuid
from pathlib import Path

import yaml

from knowledgeforge.config import AppConfig
from knowledgeforge.models import (
    CompletenessResult,
    DocumentArtifact,
    EnginePlan,
    EngineRunResult,
    KnowledgeFileState,
    RequestContext,
)
from knowledgeforge.storage.realtime_reviewer import RealtimeFileReviewer
from knowledgeforge.utils.file_contract import parse_contract_block, render_contract_block, replace_contract_block
from knowledgeforge.utils.knowledge_tree import module_directory, module_labels_by_id, plan_path_for_role
from knowledgeforge.utils.paths import ensure_directory, sanitize_path_segment, slugify_filename
from knowledgeforge.utils.time import now_iso, today_compact


class MarkdownKnowledgeWriter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def materialize_knowledge_base(
        self,
        *,
        context: RequestContext,
        round_number: int,
    ) -> list[dict[str, object]]:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        ensure_directory(domain_dir)
        states: list[dict[str, object]] = []
        timestamp = now_iso()
        for blueprint in context.knowledge_blueprint:
            relative_path = str(blueprint.get("relative_path", "")).strip()
            if not relative_path:
                continue
            file_path = domain_dir / relative_path
            ensure_directory(file_path.parent)
            if not file_path.exists():
                file_path.write_text(
                    self._render_blueprint_skeleton(
                        context=context,
                        blueprint=blueprint,
                        round_number=round_number,
                        file_path=file_path,
                        timestamp=timestamp,
                    ),
                    encoding="utf-8",
                )
            contract = parse_contract_block(file_path.read_text(encoding="utf-8"))
            states.append(
                KnowledgeFileState(
                    file_id=str(blueprint.get("file_id", file_path.stem)),
                    file_path=file_path.as_posix(),
                    module_id=str(blueprint.get("module_id", "")),
                    subdomain=str(blueprint.get("subdomain", "")),
                    status=str((contract or {}).get("completion_status", {}).get("state", "generated")),  # type: ignore[arg-type]
                    owner_engines=[str(item) for item in blueprint.get("owner_engine_candidates", [])],
                    pending_task_ids=[
                        str(item.get("task_id", ""))
                        for item in (contract or {}).get("query_tasks", [])
                        if str(item.get("status", "")).strip() != "completed"
                    ],
                    completed_task_ids=[
                        str(item.get("task_id", ""))
                        for item in (contract or {}).get("query_tasks", [])
                        if str(item.get("status", "")).strip() == "completed"
                    ],
                ).to_dict()
            )
        return states

    def write_agent_plan_documents(
        self,
        *,
        context: RequestContext,
        plans: dict[str, EnginePlan],
        round_number: int,
    ) -> dict[str, str]:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        saved_paths: dict[str, str] = {}
        for agent_name, plan in plans.items():
            if not plan.plan_items:
                continue
            first_item = plan.plan_items[0]
            module_id = str(first_item.metadata.get("module_id", "overview"))
            subdomain = str(first_item.metadata.get("subdomain", "")) or (context.core_topics[0] if context.core_topics else "通用")
            target_dir = self._plan_document_directory(domain_dir, module_id, subdomain)
            ensure_directory(target_dir)
            title = f"{context.domain} {agent_name} 生成计划"
            document_id = f"{agent_name.lower()}-plan-{uuid.uuid4().hex[:12]}"
            filename = f"{today_compact()}-{slugify_filename(title, document_id)}-plan.md"
            document_path = target_dir / filename
            saved_paths[agent_name] = self.write_agent_plan_document(
                context=context,
                plan=plan,
                round_number=round_number,
                document_path=document_path,
                document_id=document_id,
            )
        return saved_paths

    def write_agent_plan_document(
        self,
        *,
        context: RequestContext,
        plan: EnginePlan,
        round_number: int,
        document_path: Path | str,
        document_id: str | None = None,
    ) -> str:
        document_path = Path(document_path)
        ensure_directory(document_path.parent)
        relative_path = document_path.as_posix()
        timestamp = now_iso()
        title = f"{context.domain} {plan.agent_name} 生成计划"
        front_matter = {
            "id": document_id or document_path.stem,
            "title": title,
            "domain": context.domain,
            "subdomain": context.core_topics[0] if context.core_topics else (context.subdomains[0] if context.subdomains else "通用"),
            "doc_type": "note",
            "source_type": "agent_plan",
            "agent": plan.agent_name,
            "round": round_number,
            "status": "draft",
            "created_at": plan.created_at or timestamp,
            "updated_at": timestamp,
            "version": "v1",
            "path": relative_path,
            "tags": [*context.focus_points, "agent-plan", plan.agent_name],
            "sources": [
                {
                    "title": f"{plan.agent_name} generated plan",
                    "url": f"local://{plan.agent_name.lower()}/generated-plan",
                    "publisher": "KnowledgeForge",
                    "retrieved_at": timestamp,
                    "reliability": "unknown",
                }
            ],
        }
        document_path.write_text(
            self._render_agent_plan_document(
                front_matter=front_matter,
                title=title,
                context=context,
                plan=plan,
                timestamp=timestamp,
            ),
            encoding="utf-8",
        )
        return relative_path

    def write(
        self,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
        completeness: CompletenessResult,
        round_number: int,
    ) -> DocumentArtifact:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        generated_files = [item["file_path"] for item in self.materialize_knowledge_base(context=context, round_number=round_number)]
        self._apply_output_artifacts(context, outputs)
        subdomain = context.core_topics[0] if context.core_topics else (context.subdomains[0] if context.subdomains else "通用")
        subdomain_dir = domain_dir / "02_core_topics" / sanitize_path_segment(subdomain, "general")
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
            module_id="core_topics",
            module_label="Core Topics",
            doc_role="topic_article",
            generated_files=generated_files,
        )

        document_body = self._render_document(artifact, context, outputs, completeness, round_number)
        navigation_paths = self._write_navigation_documents(context, outputs, domain_dir)
        artifact.navigation_paths = navigation_paths
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
        document_path.write_text(document_body, encoding="utf-8")
        return artifact

    def _render_blueprint_skeleton(
        self,
        *,
        context: RequestContext,
        blueprint: dict[str, object],
        round_number: int,
        file_path: Path,
        timestamp: str,
    ) -> str:
        title = str(blueprint.get("title", file_path.stem))
        subdomain = str(blueprint.get("subdomain", ""))
        source_type = "mixed" if "QueryEngine" in blueprint.get("owner_engine_candidates", []) else "insight"
        front_matter = {
            "id": str(blueprint.get("file_id", file_path.stem)),
            "title": title,
            "domain": context.domain,
            "subdomain": subdomain,
            "doc_type": str(blueprint.get("doc_type", "article")),
            "source_type": source_type,
            "agent": "KnowledgeForge",
            "round": round_number,
            "status": "draft",
            "created_at": timestamp,
            "updated_at": timestamp,
            "version": "v1",
            "path": file_path.as_posix(),
            "tags": [str(blueprint.get("module_id", "")), *(context.focus_points or [])],
            "sources": [
                {
                    "title": "Knowledge blueprint scaffold",
                    "url": "local://knowledge-blueprint",
                    "publisher": "KnowledgeForge",
                    "retrieved_at": timestamp,
                    "reliability": "unknown",
                }
            ],
        }
        contract = self._initial_contract(context, blueprint, file_path)
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        body_title = f"# {title}"
        return "\n".join(
            [
                "---",
                front_matter_text,
                "---",
                "",
                body_title,
                "",
                "## 摘要",
                "",
                "该文件是根据知识库蓝图自动生成的骨架文档，后续会由对应 Engine 按职责逐步补全。",
                "",
                "## 关键结论",
                "",
                "- 当前为骨架状态。",
                "- 需要结合来源与查询任务补齐证据。",
                "",
                "## 背景与上下文",
                "",
                f"- 模块：{blueprint.get('module_label', blueprint.get('module_id', ''))}",
                f"- 子领域：{subdomain or '通用'}",
                f"- 负责 Engine：{', '.join(str(item) for item in blueprint.get('owner_engine_candidates', [])) or '未指定'}",
                "",
                "## 正文",
                "",
                f"### {title}",
                "",
                "待补充。",
                "",
                "## 证据与来源",
                "",
                "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |",
                "|---|---|---|---|---|",
                "| S0 | Blueprint scaffold | 初始骨架生成 | unknown | 待补充真实来源 |",
                "",
                "## 实体与关系候选",
                "",
                "### 实体候选",
                "",
                "| 实体 | 类型 | 描述 | 来源 |",
                "|---|---|---|---|",
                f"| {context.domain} | Domain | 目标领域 | S0 |",
                "",
                "### 关系候选",
                "",
                "| 主体 | 关系 | 客体 | 来源 |",
                "|---|---|---|---|",
                f"| {context.domain} | contains | {title} | S0 |",
                "",
                "## 冲突与不确定性",
                "",
                "- 待补充。",
                "",
                "## 后续动作",
                "",
                "- 根据 JSON 合同中的 query_tasks 补证据。",
                "",
                render_contract_block(contract),
                "",
                "## 变更记录",
                "",
                "| 版本 | 时间 | 变更说明 |",
                "|---|---|---|",
                f"| v1 | {timestamp[:10]} | 初始骨架创建 |",
                "",
            ]
        )

    def _initial_contract(
        self,
        context: RequestContext,
        blueprint: dict[str, object],
        file_path: Path,
    ) -> dict[str, object]:
        section_plan = ["摘要", "关键结论", "背景与上下文", "正文", "证据与来源", "冲突与不确定性", "后续动作"]
        query_tasks: list[dict[str, object]] = []
        requirements = blueprint.get("completion_requirements", {})
        query_task_count = 0
        if isinstance(requirements, dict):
            query_task_count = int(requirements.get("required_query_tasks", 0) or 0)
        if query_task_count > 0:
            query_tasks.append(
                {
                    "task_id": f"{blueprint.get('file_id', file_path.stem)}-query-1",
                    "file_path": file_path.as_posix(),
                    "section": "证据与来源",
                    "claim_or_gap": f"为 {blueprint.get('title', file_path.stem)} 补充可追溯权威依据",
                    "query_intent": f"{context.domain} {blueprint.get('subdomain') or blueprint.get('title')} 官方资料",
                    "expected_evidence": ["官方定义", "权威说明", "来源链接"],
                    "preferred_source_types": ["official documentation", "standard", "vendor docs"],
                    "acceptance_criteria": ["至少命中一个中高可信来源", "结论可回写到文档证据表"],
                    "status": "planned",
                }
            )
        return {
            "file_id": str(blueprint.get("file_id", file_path.stem)),
            "file_path": file_path.as_posix(),
            "section_plan": section_plan,
            "claims": [f"{blueprint.get('title', file_path.stem)} 需要形成清晰、可追溯的知识说明。"],
            "evidence_needed": ["权威定义", "关键结论对应来源", "必要时补充案例或趋势背景"],
            "query_tasks": query_tasks,
            "engine_contributions": {
                "InsightEngine": "负责背景、结构骨架和本地知识线索",
                "QueryEngine": "负责权威事实和证据闭环",
                "MediaEngine": "负责趋势、社区观点和案例语境",
            },
            "completion_status": {
                "state": "generated",
                "required": bool(isinstance(requirements, dict) and requirements.get("required")),
                "completed_task_ids": [],
                "pending_task_ids": [str(item["task_id"]) for item in query_tasks],
            },
        }

    def _apply_output_artifacts(self, context: RequestContext, outputs: dict[str, EngineRunResult]) -> None:
        for agent_name, output in outputs.items():
            for artifact in output.artifacts:
                file_path = self._resolve_artifact_path(str(artifact.get("target_file_path", "")).strip())
                if not file_path.exists():
                    continue
                text = file_path.read_text(encoding="utf-8")
                contract = parse_contract_block(text)
                if contract is None:
                    continue
                task_updates = {str(item.get("task_id", "")): item for item in artifact.get("task_updates", [])}
                for task in contract.get("query_tasks", []):
                    task_id = str(task.get("task_id", ""))
                    update = task_updates.get(task_id)
                    if update:
                        task["status"] = update.get("status", task.get("status", "planned"))
                        if update.get("citation"):
                            task["citation"] = update["citation"]
                status = str(artifact.get("state", contract.get("completion_status", {}).get("state", "generated")))
                completed = [str(item.get("task_id", "")) for item in contract.get("query_tasks", []) if str(item.get("status", "")) == "completed"]
                pending = [str(item.get("task_id", "")) for item in contract.get("query_tasks", []) if str(item.get("status", "")) != "completed"]
                contract["completion_status"] = {
                    **contract.get("completion_status", {}),
                    "state": status,
                    "completed_task_ids": completed,
                    "pending_task_ids": pending,
                    "updated_by": agent_name,
                }
                updated_text = replace_contract_block(text, contract)
                contribution = str(artifact.get("content", "")).strip()
                if contribution:
                    updated_text = self._append_agent_contribution(updated_text, agent_name, contribution)
                file_path.write_text(updated_text, encoding="utf-8")

    def _resolve_artifact_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.exists():
            return candidate
        normalized = path.replace("\\", "/").strip()
        if normalized.startswith("save/"):
            return self._config.save_root / normalized[len("save/") :]
        return candidate

    @staticmethod
    def _append_agent_contribution(text: str, agent_name: str, contribution: str) -> str:
        marker = f"### {agent_name} 贡献"
        if marker in text:
            return text
        insert_at = "## 证据与来源"
        block = "\n".join([marker, "", contribution, ""])
        if insert_at in text:
            return text.replace(insert_at, f"{block}\n{insert_at}", 1)
        return f"{text}\n{block}\n"

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
    def _render_agent_plan_document(
        *,
        front_matter: dict,
        title: str,
        context: RequestContext,
        plan: EnginePlan,
        timestamp: str,
    ) -> str:
        front_matter_text = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).strip()
        plan_rows = [
            "| {id} | {title} | {query} | {targets} | {criteria} | {fallbacks} | {status} |".format(
                id=item.plan_item_id.replace("|", "\\|"),
                title=item.title.replace("|", "\\|"),
                query=item.query_or_action.replace("|", "\\|"),
                targets="; ".join(item.targets).replace("|", "\\|"),
                criteria="; ".join(item.success_criteria).replace("|", "\\|"),
                fallbacks="; ".join(item.fallbacks).replace("|", "\\|"),
                status=item.status,
            )
            for item in plan.plan_items
        ]
        plan_lines: list[str] = []
        for item in plan.plan_items:
            marker = "☑" if item.status == "completed" else "☐"
            plan_lines.extend(
                [
                    f"- {marker} {item.plan_item_id} [{item.status}] {item.title}",
                    f"  查询/动作：{item.query_or_action}",
                    f"  查询内容：{'; '.join(item.targets) if item.targets else '未指定'}",
                    f"  满足标准：{'; '.join(item.success_criteria) if item.success_criteria else '未指定'}",
                ]
            )
            if item.metadata.get("subdomain"):
                plan_lines.append(f"  子领域：{item.metadata.get('subdomain')}")
            if item.metadata.get("url"):
                plan_lines.append(f"  URL：{item.metadata.get('url')}")
            if item.metadata.get("planned_path"):
                plan_lines.append(f"  计划保存路径：{item.metadata.get('planned_path')}")
            if item.fallbacks:
                plan_lines.append(f"  补查查询：{'; '.join(item.fallbacks)}")
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
                f"本文档保存 {context.domain} / {', '.join(context.core_topics or context.subdomains)} 在本轮 {plan.agent_name} 执行前生成的计划。",
                "它用于用户确认、执行审计和后续质量回溯，不等同于已验证知识结论。",
                "",
                "## 关键结论",
                "",
                f"- {plan.agent_name} 生成 {len(plan.plan_items)} 个计划项。",
                f"- 计划状态：{plan.status}。",
                "- 每个计划项保留查询/动作、查询内容、满足标准和补查路径。",
                "",
                "## 背景与上下文",
                "",
                f"领域：{context.domain}",
                f"子领域：{', '.join(context.core_topics or context.subdomains)}",
                f"时间范围：{context.time_window}",
                f"生成时间：{timestamp}",
                "",
                "## 正文",
                "",
                "### 生成理由",
                "",
                plan.reasoning or "无",
                "",
                "### 计划清单",
                "",
                *plan_lines,
                "",
                "### 结构化表格",
                "",
                "| 编号 | 标题 | 查询/动作 | 查询内容 | 满足标准 | 补查路径 | 状态 |",
                "|---|---|---|---|---|---|---|",
                *plan_rows,
                "",
                "## 证据与来源",
                "",
                "| 编号 | 来源 | 关键信息 | 可信度 | 备注 |",
                "|---|---|---|---|---|",
                f"| S1 | {plan.agent_name} generated plan | 用户确认前生成的执行计划 | unknown | 本地计划文档 |",
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
                f"| {plan.agent_name} | planned_for | {context.domain} | S1 |",
                "",
                "## 冲突与不确定性",
                "",
                "- 计划项只代表待执行的查询或动作，需要通过后续采集与质量检查验证。",
                "",
                "## 后续动作",
                "",
                "- 用户确认计划后再进入并行采集。",
                "",
                "## 变更记录",
                "",
                "| 版本 | 时间 | 变更说明 |",
                "|---|---|---|",
                f"| v1 | {timestamp[:10]} | 初始创建 |",
                "",
            ]
        )

    @staticmethod
    def _extract_query_plan_lines(raw_material: list[str]) -> list[str]:
        heading = "链接级采集计划：" if "链接级采集计划：" in raw_material else "查询计划："
        if heading not in raw_material:
            return []
        start = raw_material.index(heading) + 1
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
                f"本文档保存 {context.domain} / {', '.join(context.core_topics or context.subdomains)} 在本轮 QueryEngine 执行前生成的链接级采集计划、预期信息和执行状态。",
                "它用于审计查询决策，不等同于已验证知识结论。",
                "",
                "## 关键结论",
                "",
                "- QueryEngine 已在检索前生成结构化链接级采集计划。",
                "- 每个计划项保留目标 URL、所属子领域、预期信息、满足标准和计划保存路径。",
                "- 执行事件可用于判断哪些文章级计划项已满足、哪些仍需补检索。",
                "",
                "## 背景与上下文",
                "",
                f"领域：{context.domain}",
                f"子领域：{', '.join(context.core_topics or context.subdomains)}",
                f"时间范围：{context.time_window}",
                f"生成时间：{timestamp}",
                "",
                "## 正文",
                "",
                "### 链接级采集计划",
                "",
                *(query_plan_lines or ["- 暂无结构化链接级采集计划。"]),
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
                "- 该计划只代表待执行的文章级采集决策，不能替代已验证事实。",
                "",
                "## 后续动作",
                "",
                "- 对 status=insufficient 的计划项执行补检索或人工复核。",
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
            f"本文围绕 {context.domain} 生成首版知识综述，覆盖 {', '.join(context.core_topics or context.subdomains)}。",
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
            if agent_name == "QueryEngine":
                aggregated_query_docs = self._render_saved_query_articles(context)
                if aggregated_query_docs:
                    body_sections.append(aggregated_query_docs)
                    continue
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
        for subdomain in (context.core_topics or context.subdomains):
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
                f"模块：{artifact.module_label or artifact.module_id}",
                f"子领域：{artifact.subdomain}",
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
                f"| {artifact.module_label or artifact.module_id} | KnowledgeModule | 知识模块 | S1 |",
                *[
                    f"| {subdomain} | SubTopic | 领域子主题 | S1 |"
                    for subdomain in (context.core_topics or context.subdomains)
                ],
                "",
                "### 关系候选",
                "",
                "| 主体 | 关系 | 客体 | 来源 |",
                "|---|---|---|---|",
                f"| {context.domain} | has_module | {artifact.module_label or artifact.module_id} | S1 |",
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

    def _render_saved_query_articles(self, context: RequestContext) -> str:
        domain_dir = self._config.save_root / sanitize_path_segment(context.domain, "domain")
        realtime_docs = [
            item for item in RealtimeFileReviewer.scan_realtime_documents(domain_dir) if item.get("agent") == "QueryEngine"
        ]
        if not realtime_docs:
            return ""
        lines = [
            "### QueryEngine",
            "以下内容基于已保存的文章级 Query 文档聚合，不再直接把原始查询计划当作主知识载体。",
            "",
            "#### 已保存文章",
        ]
        lines.extend(
            f"- {item['title']} | {item['subdomain']} | {item['url']} | {item['path']}"
            for item in realtime_docs[:10]
        )
        return "\n".join(lines)

    @staticmethod
    def _readable_raw_material(agent_name: str, raw_material: list[str]) -> list[str]:
        if agent_name != "QueryEngine":
            return raw_material
        readable: list[str] = []
        skipping_query_plan = False
        skipped_plan_lines = 0
        for item in raw_material:
            if item in {"查询计划：", "链接级采集计划："}:
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

    def _render_domain_readme(
        self,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
        domain_dir: Path,
    ) -> str:
        if RealtimeFileReviewer.scan_realtime_documents(domain_dir):
            return RealtimeFileReviewer.render_domain_index(context, domain_dir)
        sections = "\n".join(f"- {topic}" for topic in (context.core_topics or context.subdomains))
        sources = sum(len(output.sources) for output in outputs.values())
        return "\n".join(
            [
                f"# {context.domain}",
                "",
                "## 领域概览",
                "",
                f"当前领域目录用于保存 {context.domain} 的知识文档与索引信息。",
                f"已规划模块：{', '.join(item['directory'] for item in context.knowledge_modules)}。",
                f"已规划核心主题：{', '.join(context.core_topics or context.subdomains)}。",
                f"当前批次已汇总来源数量：{sources}。",
                "",
                "## 核心主题",
                "",
                sections,
                "",
            ]
        )

    def _write_navigation_documents(
        self,
        context: RequestContext,
        outputs: dict[str, EngineRunResult],
        domain_dir: Path,
    ) -> list[str]:
        ensure_directory(domain_dir)
        paths: list[str] = []
        readme_path = domain_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(self._render_domain_readme(context, outputs, domain_dir), encoding="utf-8")
        paths.append(readme_path.as_posix())
        domain_index_path = domain_dir / "index.md"
        if not domain_index_path.exists():
            domain_index_path.write_text(RealtimeFileReviewer.render_domain_navigation(context, domain_dir), encoding="utf-8")
        paths.append(domain_index_path.as_posix())
        for module in context.knowledge_modules:
            module_dir = domain_dir / module["directory"]
            ensure_directory(module_dir)
            module_readme = module_dir / "README.md"
            module_index = module_dir / "index.md"
            if not module_readme.exists():
                module_readme.write_text(
                    RealtimeFileReviewer.render_module_overview(context, module["module_id"], module_dir),
                    encoding="utf-8",
                )
            if not module_index.exists():
                module_index.write_text(
                    RealtimeFileReviewer.render_module_index(context, module["module_id"], module_dir),
                    encoding="utf-8",
                )
            paths.extend([module_readme.as_posix(), module_index.as_posix()])
        for topic in (context.core_topics or context.subdomains):
            topic_dir = domain_dir / "02_core_topics" / sanitize_path_segment(topic, "topic")
            ensure_directory(topic_dir)
            topic_readme = topic_dir / "README.md"
            topic_index = topic_dir / "index.md"
            if not topic_readme.exists():
                topic_readme.write_text(
                    RealtimeFileReviewer.render_subdomain_overview(context, topic_dir, topic),
                    encoding="utf-8",
                )
            if not topic_index.exists():
                topic_index.write_text(
                    RealtimeFileReviewer.render_subdomain_index(context, topic_dir, topic),
                    encoding="utf-8",
                )
            paths.extend([topic_readme.as_posix(), topic_index.as_posix()])
        return paths

    @staticmethod
    def _plan_document_directory(domain_dir: Path, module_id: str, subdomain: str) -> Path:
        module_dir = domain_dir / module_directory(module_id)
        if module_id == "core_topics":
            return module_dir / sanitize_path_segment(subdomain or "topic", "topic")
        return module_dir
