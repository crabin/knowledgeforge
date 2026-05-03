from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROMPT_PROFILE_VERSION = "knowledge-file-profile-v2"


@dataclass(frozen=True, slots=True)
class KnowledgeFilePromptSpec:
    relative_path: str
    title: str
    doc_role: str
    required_sections: list[str]
    must_cover: list[str]
    query_hint_rules: list[str]
    allowed_agent_tasks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "title": self.title,
            "doc_role": self.doc_role,
            "required_sections": list(self.required_sections),
            "must_cover": list(self.must_cover),
            "query_hint_rules": list(self.query_hint_rules),
            "allowed_agent_tasks": list(self.allowed_agent_tasks),
        }


DEFAULT_REQUIRED_SECTIONS = [
    "摘要",
    "关键结论",
    "背景与上下文",
    "正文",
    "证据与来源",
    "冲突与不确定性",
    "后续动作",
]

FRAMEWORK_REQUIRED_SECTIONS = [
    "知识定位",
    "学习角色与路径",
    "知识关系",
    "证据与来源",
    "冲突与不确定性",
    "后续动作",
]

DEFAULT_QUERY_HINT_RULES = [
    "所有关键结论必须预留可追溯依据槽位。",
    "query_tasks 必须为严格 JSON 数组，且每个任务只绑定一个目标文件与章节。",
    "如果需要官方事实闭环，则 task_type 使用 query；如果需要趋势、社区观点或案例语境，则 task_type 使用 media。",
]

FRAMEWORK_QUERY_HINT_RULES = [
    "只生成知识框架证据文件，不展开完整正文或长篇解释。",
    "证据优先使用官方文档、标准、规范、权威论文或项目主页。",
    "query_tasks 必须为严格 JSON 数组，且每个任务只绑定一个目标文件与证据章节。",
    "除非明确需要趋势、案例或社区观点，否则 task_type 使用 query。",
]


ROLE_MUST_COVER: dict[str, list[str]] = {
    "domain_overview": ["领域定义", "整体结构导航", "学习/阅读路径", "重点文件入口"],
    "domain_index": ["目录索引", "模块映射", "文件状态追踪", "队列与补证据入口"],
    "module_overview": ["模块目标", "模块内文件导航", "该模块学习建议", "与其他模块关系"],
    "module_index": ["模块目录清单", "文件用途", "状态与更新说明"],
    "topic_overview": ["主题定位", "主题内文件导航", "学习路径", "待补证据概览"],
    "topic_index": ["主题文件索引", "章节说明", "证据缺口提醒"],
    "module_doc": ["本文件核心概念", "结构化结论", "依据待补充点", "与上下游知识关系"],
    "topic_article": ["主题定义", "关键方法/机制", "应用/限制", "论文/项目/工具入口"],
}


ROLE_ALLOWED_AGENT_TASKS: dict[str, list[str]] = {
    "domain_overview": ["query", "media"],
    "domain_index": ["query"],
    "module_overview": ["query", "media"],
    "module_index": ["query"],
    "topic_overview": ["query", "media"],
    "topic_index": ["query"],
    "module_doc": ["query", "media"],
    "topic_article": ["query", "media"],
}


def build_prompt_spec(blueprint: dict[str, Any], completion_mode: str = "framework") -> KnowledgeFilePromptSpec:
    relative_path = str(blueprint.get("relative_path", "")).strip()
    title = str(blueprint.get("title", "")).strip() or relative_path
    doc_role = str(blueprint.get("doc_role", "module_doc")).strip() or "module_doc"
    filename = relative_path.split("/")[-1] if relative_path else title
    framework_mode = completion_mode == "framework"
    required_sections = list(FRAMEWORK_REQUIRED_SECTIONS if framework_mode else DEFAULT_REQUIRED_SECTIONS)
    must_cover = list(ROLE_MUST_COVER.get(doc_role, ROLE_MUST_COVER["module_doc"]))
    must_cover.extend(_filename_specific_requirements(filename))
    if framework_mode:
        must_cover.extend(["学习顺序定位", "前置知识关系", "官方证据入口", "后续补全文档所需素材"])
    return KnowledgeFilePromptSpec(
        relative_path=relative_path,
        title=title,
        doc_role=doc_role,
        required_sections=required_sections,
        must_cover=_dedupe(must_cover),
        query_hint_rules=list(FRAMEWORK_QUERY_HINT_RULES if framework_mode else DEFAULT_QUERY_HINT_RULES),
        allowed_agent_tasks=list(ROLE_ALLOWED_AGENT_TASKS.get(doc_role, ["query"])),
    )


def build_generation_system_prompt(completion_mode: str = "framework") -> str:
    if completion_mode == "framework":
        return (
            "你是 KnowledgeForge 知识框架证据文件生成器。"
            "请基于给定文件规范输出严格 JSON，字段必须包含 markdown、query_tasks、claims、evidence_needed、completion_status。"
            "markdown 必须是证据型 Markdown 文本，包含 YAML front matter 与 knowledgeforge:contract 注释块。"
            "只写知识定位、学习角色/路径、知识关系、证据与来源、后续动作；不要生成完整正文、长篇教程或总结型文章。"
            "query_tasks 必须优先检索官方文档、标准、规范、权威论文或项目主页。"
            "query_tasks 每项包含 task_id、task_type、section、claim_or_gap、query_text、expected_evidence、preferred_source_types、acceptance_criteria、status。"
        )
    return (
        "你是 KnowledgeForge 文件骨架生成器。"
        "请基于给定文件规范输出严格 JSON，字段必须包含 markdown、query_tasks、claims、evidence_needed、completion_status。"
        "markdown 必须是完整 Markdown 文本，包含 YAML front matter 与 \"## 知识文件合同\" JSON 代码块。"
        "query_tasks 必须是数组，每项包含 task_id、task_type、section、claim_or_gap、query_text、expected_evidence、preferred_source_types、acceptance_criteria、status。"
    )


def build_structure_graph_system_prompt() -> str:
    return (
        "你是 KnowledgeForge 领域知识框架图谱规划器。"
        "请根据用户意图生成用于整体学习规划、本地知识库目录和文件蓝图的结构图谱，输出严格 JSON。"
        "JSON 必须包含 nodes、edges、root_node_id、source_intent。"
        "nodes 中每个节点必须包含 node_id、title、node_type、relative_path、doc_type、owner_engine_candidates、required_query_tasks。"
        "nodes 应在 metadata 中尽量给出 learning_role、learning_order、prerequisites、official_evidence_targets。"
        "node_type 只能是 domain、section、subtopic、article、index；edge_type 只能是 CONTAINS、INDEXES、RELATED_TO。"
        "relative_path 必须是相对 Markdown 路径，禁止绝对路径和 ..；根 domain 节点必须使用 README.md。"
        "图谱要让读者一眼看出该领域需要学习哪些知识、先后关系、学习角色和证据入口。"
    )


def build_validation_system_prompt() -> str:
    return (
        "你是 KnowledgeForge 文件完整性验证器。"
        "请输出严格 JSON，字段必须包含 is_complete、missing_evidence、new_tasks、reasoning、file_status_updates。"
        "只有当关键结论均有可追溯来源且必需任务完成时，is_complete 才能为 true。"
    )


def _filename_specific_requirements(filename: str) -> list[str]:
    rules: dict[str, list[str]] = {
        "README.md": ["必须能让读者快速理解当前目录用途与阅读顺序。"],
        "index.md": ["必须包含清晰的文件清单和状态说明。"],
        "08_glossary.md": ["必须给出术语、简短定义和适用语境。"],
        "04_recent_papers.md": ["必须强调时效性、论文筛选标准和代表性来源。"],
        "08_reference_list.md": ["必须以引用清单为核心，适合补充来源追溯。"],
        "04_interview_questions.md": ["必须体现高频问题、考察点和答题方向。"],
    }
    return rules.get(filename, [])


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped
