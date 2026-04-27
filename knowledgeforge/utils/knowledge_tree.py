from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledgeforge.utils.paths import sanitize_path_segment, slugify_filename


@dataclass(frozen=True, slots=True)
class KnowledgeModuleDefinition:
    module_id: str
    label: str
    directory: str
    purpose: str
    priority: str
    default_doc_type: str = "article"


@dataclass(frozen=True, slots=True)
class NavigationTargetDefinition:
    doc_role: str
    title: str
    relative_path: str
    module_id: str = ""
    module_label: str = ""
    subdomain: str = ""
    doc_type: str = "article"


DEFAULT_KNOWLEDGE_MODULES: tuple[KnowledgeModuleDefinition, ...] = (
    KnowledgeModuleDefinition("overview", "Overview", "00_overview", "领域背景与整体理解", "high"),
    KnowledgeModuleDefinition("foundations", "Foundations", "01_foundations", "基础理论与先修知识", "high"),
    KnowledgeModuleDefinition("core_topics", "Core Topics", "02_core_topics", "核心主题与主干方法", "high"),
    KnowledgeModuleDefinition("advanced_topics", "Advanced Topics", "03_advanced_topics", "前沿方向与延展议题", "medium"),
    KnowledgeModuleDefinition("papers", "Papers", "04_papers", "经典论文、综述与最新研究", "medium"),
    KnowledgeModuleDefinition("projects", "Projects", "05_projects", "项目实践与能力转化", "medium"),
    KnowledgeModuleDefinition("tools", "Tools", "06_tools", "工具、框架与数据资源", "medium"),
    KnowledgeModuleDefinition("review", "Review", "07_review", "复习、总结与问题清单", "low"),
)


MODULE_BY_ID = {item.module_id: item for item in DEFAULT_KNOWLEDGE_MODULES}


def build_default_modules() -> list[dict[str, str]]:
    return [
        {
            "module_id": module.module_id,
            "label": module.label,
            "directory": module.directory,
            "purpose": module.purpose,
            "priority": module.priority,
            "default_doc_type": module.default_doc_type,
        }
        for module in DEFAULT_KNOWLEDGE_MODULES
    ]


def normalize_core_topics(subdomains: list[str], fallback_domain: str) -> list[str]:
    cleaned = [topic.strip() for topic in subdomains if topic.strip()]
    return cleaned or [fallback_domain]


def build_navigation_targets(domain: str, core_topics: list[str]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = [
        {
            "doc_role": "domain_overview",
            "title": f"{domain} Overview",
            "relative_path": "README.md",
            "doc_type": "summary",
        },
        {
            "doc_role": "domain_index",
            "title": f"{domain} Index",
            "relative_path": "index.md",
            "doc_type": "note",
        },
    ]
    for module in DEFAULT_KNOWLEDGE_MODULES:
        targets.extend(
            [
                {
                    "doc_role": "module_overview",
                    "title": f"{domain} {module.label}",
                    "relative_path": f"{module.directory}/README.md",
                    "module_id": module.module_id,
                    "module_label": module.label,
                    "doc_type": "summary",
                },
                {
                    "doc_role": "module_index",
                    "title": f"{domain} {module.label} Index",
                    "relative_path": f"{module.directory}/index.md",
                    "module_id": module.module_id,
                    "module_label": module.label,
                    "doc_type": "note",
                },
            ]
        )
    for topic in core_topics:
        topic_segment = sanitize_path_segment(topic, "topic")
        targets.extend(
            [
                {
                    "doc_role": "topic_overview",
                    "title": f"{topic} Overview",
                    "relative_path": f"02_core_topics/{topic_segment}/README.md",
                    "module_id": "core_topics",
                    "module_label": "Core Topics",
                    "subdomain": topic,
                    "doc_type": "summary",
                },
                {
                    "doc_role": "topic_index",
                    "title": f"{topic} Index",
                    "relative_path": f"02_core_topics/{topic_segment}/index.md",
                    "module_id": "core_topics",
                    "module_label": "Core Topics",
                    "subdomain": topic,
                    "doc_type": "note",
                },
            ]
        )
    return targets


def module_directory(module_id: str) -> str:
    module = MODULE_BY_ID.get(module_id)
    return module.directory if module is not None else "99_misc"


def plan_path_for_role(
    *,
    save_root: Path,
    domain: str,
    module_id: str,
    subdomain: str,
    doc_role: str,
    title: str,
    suffix: str,
) -> str:
    domain_dir = save_root / sanitize_path_segment(domain, "domain")
    if doc_role == "domain_overview":
        return (domain_dir / "README.md").as_posix()
    if doc_role == "domain_index":
        return (domain_dir / "index.md").as_posix()
    if doc_role == "module_overview":
        return (domain_dir / module_directory(module_id) / "README.md").as_posix()
    if doc_role == "module_index":
        return (domain_dir / module_directory(module_id) / "index.md").as_posix()
    if doc_role == "topic_overview":
        return (
            domain_dir / "02_core_topics" / sanitize_path_segment(subdomain or "topic", "topic") / "README.md"
        ).as_posix()
    if doc_role == "topic_index":
        return (
            domain_dir / "02_core_topics" / sanitize_path_segment(subdomain or "topic", "topic") / "index.md"
        ).as_posix()
    target_dir = domain_dir / module_directory(module_id)
    if subdomain:
        target_dir = target_dir / sanitize_path_segment(subdomain, "topic")
    filename = f"{slugify_filename(title, suffix)}.md"
    return (target_dir / filename).as_posix()


def module_labels_by_id() -> dict[str, str]:
    return {module.module_id: module.label for module in DEFAULT_KNOWLEDGE_MODULES}
