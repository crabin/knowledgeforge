from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledgeforge.server.models import KnowledgeFileBlueprint
from knowledgeforge.server.utils.paths import sanitize_path_segment, slugify_filename


@dataclass(frozen=True, slots=True)
class KnowledgeModuleDefinition:
    module_id: str
    label: str
    directory: str
    purpose: str
    priority: str
    default_doc_type: str = "article"


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

MODULE_FILE_TEMPLATES: dict[str, list[tuple[str, str, str, list[str], bool]]] = {
    "overview": [
        ("01_field_definition.md", "Field Definition", "module_doc", ["InsightEngine"], False),
        ("02_development_history.md", "Development History", "module_doc", ["InsightEngine"], False),
        ("03_current_research_status.md", "Current Research Status", "module_doc", ["MediaEngine"], False),
        ("04_application_areas.md", "Application Areas", "module_doc", ["QueryEngine", "MediaEngine"], False),
        ("05_industry_value.md", "Industry Value", "module_doc", ["InsightEngine"], False),
        ("06_key_challenges.md", "Key Challenges", "module_doc", ["MediaEngine"], False),
        ("07_learning_roadmap.md", "Learning Roadmap", "module_doc", ["InsightEngine"], False),
        ("08_glossary.md", "Glossary", "module_doc", ["QueryEngine"], False),
    ],
    "foundations": [
        ("01_mathematics.md", "Mathematics", "module_doc", ["InsightEngine"], False),
        ("02_programming_basics.md", "Programming Basics", "module_doc", ["InsightEngine"], False),
        ("03_domain_background.md", "Domain Background", "module_doc", ["InsightEngine"], False),
        ("04_basic_concepts.md", "Basic Concepts", "module_doc", ["QueryEngine"], False),
        ("05_basic_algorithms.md", "Basic Algorithms", "module_doc", ["QueryEngine"], False),
        ("06_data_and_datasets.md", "Data and Datasets", "module_doc", ["QueryEngine"], False),
        ("07_evaluation_metrics.md", "Evaluation Metrics", "module_doc", ["QueryEngine"], False),
        ("08_common_workflow.md", "Common Workflow", "module_doc", ["InsightEngine"], False),
    ],
    "advanced_topics": [
        ("01_advanced_topic_map.md", "Advanced Topic Map", "module_doc", ["InsightEngine"], False),
        ("02_frontier_directions.md", "Frontier Directions", "module_doc", ["MediaEngine"], False),
        ("03_open_problems.md", "Open Problems", "module_doc", ["MediaEngine"], False),
        ("04_research_trends.md", "Research Trends", "module_doc", ["MediaEngine"], False),
        ("05_interdisciplinary_topics.md", "Interdisciplinary Topics", "module_doc", ["InsightEngine"], False),
        ("06_optimization_and_efficiency.md", "Optimization and Efficiency", "module_doc", ["QueryEngine"], False),
        ("07_security_and_robustness.md", "Security and Robustness", "module_doc", ["QueryEngine"], False),
        ("08_interpretability.md", "Interpretability", "module_doc", ["QueryEngine"], False),
        ("09_future_directions.md", "Future Directions", "module_doc", ["MediaEngine"], False),
    ],
    "papers": [
        ("01_paper_reading_guide.md", "Paper Reading Guide", "module_doc", ["InsightEngine"], False),
        ("02_classic_papers.md", "Classic Papers", "module_doc", ["QueryEngine"], False),
        ("03_survey_papers.md", "Survey Papers", "module_doc", ["QueryEngine"], False),
        ("04_recent_papers.md", "Recent Papers", "module_doc", ["QueryEngine", "MediaEngine"], False),
        ("06_paper_comparison.md", "Paper Comparison", "module_doc", ["InsightEngine"], False),
        ("07_research_gap_summary.md", "Research Gap Summary", "module_doc", ["MediaEngine"], False),
        ("08_reference_list.md", "Reference List", "module_doc", ["QueryEngine"], False),
    ],
    "projects": [
        ("01_project_roadmap.md", "Project Roadmap", "module_doc", ["InsightEngine"], False),
        ("02_beginner_projects.md", "Beginner Projects", "module_doc", ["MediaEngine"], False),
        ("03_intermediate_projects.md", "Intermediate Projects", "module_doc", ["MediaEngine"], False),
        ("04_advanced_projects.md", "Advanced Projects", "module_doc", ["MediaEngine"], False),
        ("05_research_projects.md", "Research Projects", "module_doc", ["MediaEngine"], False),
        ("06_project_template.md", "Project Template", "module_doc", ["InsightEngine"], False),
        ("07_experiment_records.md", "Experiment Records", "module_doc", ["InsightEngine"], False),
        ("08_result_analysis.md", "Result Analysis", "module_doc", ["InsightEngine"], False),
        ("09_project_summary.md", "Project Summary", "module_doc", ["InsightEngine"], False),
    ],
    "tools": [
        ("01_environment_setup.md", "Environment Setup", "module_doc", ["InsightEngine"], False),
        ("02_core_libraries.md", "Core Libraries", "module_doc", ["QueryEngine"], False),
        ("03_frameworks.md", "Frameworks", "module_doc", ["QueryEngine"], False),
        ("04_development_tools.md", "Development Tools", "module_doc", ["InsightEngine"], False),
        ("05_experiment_tools.md", "Experiment Tools", "module_doc", ["InsightEngine"], False),
        ("06_visualization_tools.md", "Visualization Tools", "module_doc", ["InsightEngine"], False),
        ("07_deployment_tools.md", "Deployment Tools", "module_doc", ["QueryEngine"], False),
        ("08_debugging_tools.md", "Debugging Tools", "module_doc", ["InsightEngine"], False),
        ("09_best_practices.md", "Best Practices", "module_doc", ["InsightEngine"], False),
    ],
    "review": [
        ("01_key_concepts_summary.md", "Key Concepts Summary", "module_doc", ["InsightEngine"], False),
        ("02_knowledge_graph.md", "Knowledge Graph", "module_doc", ["InsightEngine"], False),
        ("03_common_questions.md", "Common Questions", "module_doc", ["InsightEngine"], False),
        ("04_interview_questions.md", "Interview Questions", "module_doc", ["MediaEngine"], False),
        ("05_exam_or_quiz.md", "Exam or Quiz", "module_doc", ["InsightEngine"], False),
        ("06_mistake_notes.md", "Mistake Notes", "module_doc", ["InsightEngine"], False),
        ("07_learning_summary.md", "Learning Summary", "module_doc", ["InsightEngine"], False),
        ("08_final_report.md", "Final Report", "module_doc", ["InsightEngine"], False),
        ("09_next_learning_plan.md", "Next Learning Plan", "module_doc", ["InsightEngine"], False),
    ],
}

TOPIC_FILE_TEMPLATES: tuple[tuple[str, str, str, list[str], bool], ...] = (
    ("01_definition.md", "Definition", "topic_article", ["QueryEngine"], False),
    ("02_motivation.md", "Motivation", "topic_article", ["InsightEngine"], False),
    ("03_core_concepts.md", "Core Concepts", "topic_article", ["QueryEngine"], False),
    ("04_architecture_or_method.md", "Architecture or Method", "topic_article", ["QueryEngine"], False),
    ("05_representative_methods.md", "Representative Methods", "topic_article", ["QueryEngine"], False),
    ("06_training_or_implementation.md", "Training or Implementation", "topic_article", ["QueryEngine"], False),
    ("07_applications.md", "Applications", "topic_article", ["QueryEngine", "MediaEngine"], False),
    ("08_strengths_and_limitations.md", "Strengths and Limitations", "topic_article", ["MediaEngine"], False),
    ("09_papers.md", "Papers", "topic_article", ["QueryEngine"], False),
    ("10_projects.md", "Projects", "topic_article", ["MediaEngine"], False),
    ("11_summary.md", "Summary", "topic_article", ["InsightEngine"], False),
)


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
        {"doc_role": "domain_overview", "title": f"{domain} Overview", "relative_path": "README.md", "doc_type": "summary"},
        {"doc_role": "domain_index", "title": f"{domain} Index", "relative_path": "index.md", "doc_type": "note"},
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


def build_knowledge_blueprint(domain: str, core_topics: list[str]) -> list[dict[str, object]]:
    items: list[KnowledgeFileBlueprint] = [
        KnowledgeFileBlueprint(
            file_id=f"{sanitize_path_segment(domain, 'domain')}-domain-overview",
            title=f"{domain} Overview",
            module_id="overview",
            module_label="Overview",
            doc_role="domain_overview",
            relative_path="README.md",
            subdomain="",
            doc_type="summary",
            owner_engine_candidates=["InsightEngine"],
            completion_requirements={"required": True, "required_query_tasks": 0},
        ),
        KnowledgeFileBlueprint(
            file_id=f"{sanitize_path_segment(domain, 'domain')}-domain-index",
            title=f"{domain} Index",
            module_id="overview",
            module_label="Overview",
            doc_role="domain_index",
            relative_path="index.md",
            subdomain="",
            doc_type="note",
            owner_engine_candidates=["InsightEngine"],
            completion_requirements={"required": True, "required_query_tasks": 0},
        ),
    ]

    for module in DEFAULT_KNOWLEDGE_MODULES:
        items.extend(
            [
                KnowledgeFileBlueprint(
                    file_id=f"{module.module_id}-readme",
                    title=f"{domain} {module.label}",
                    module_id=module.module_id,
                    module_label=module.label,
                    doc_role="module_overview",
                    relative_path=f"{module.directory}/README.md",
                    subdomain="",
                    doc_type="summary",
                    owner_engine_candidates=["InsightEngine"],
                    completion_requirements={"required": True, "required_query_tasks": 0},
                ),
                KnowledgeFileBlueprint(
                    file_id=f"{module.module_id}-index",
                    title=f"{domain} {module.label} Index",
                    module_id=module.module_id,
                    module_label=module.label,
                    doc_role="module_index",
                    relative_path=f"{module.directory}/index.md",
                    subdomain="",
                    doc_type="note",
                    owner_engine_candidates=["InsightEngine"],
                    completion_requirements={"required": True, "required_query_tasks": 0},
                ),
            ]
        )
        for filename, title_suffix, doc_role, owners, required in MODULE_FILE_TEMPLATES.get(module.module_id, []):
            items.append(
                KnowledgeFileBlueprint(
                    file_id=f"{module.module_id}-{filename[:-3]}",
                    title=f"{domain} {title_suffix}",
                    module_id=module.module_id,
                    module_label=module.label,
                    doc_role=doc_role,
                    relative_path=f"{module.directory}/{filename}",
                    subdomain="",
                    doc_type="article",
                    owner_engine_candidates=owners,
                    completion_requirements={"required": required, "required_query_tasks": 0},
                )
            )

    for topic in core_topics:
        topic_segment = sanitize_path_segment(topic, "topic")
        items.extend(
            [
                KnowledgeFileBlueprint(
                    file_id=f"{topic_segment}-overview",
                    title=f"{topic} Overview",
                    module_id="core_topics",
                    module_label="Core Topics",
                    doc_role="topic_overview",
                    relative_path=f"02_core_topics/{topic_segment}/README.md",
                    subdomain=topic,
                    doc_type="summary",
                    owner_engine_candidates=["QueryEngine", "InsightEngine"],
                    completion_requirements={"required": True, "required_query_tasks": 1},
                ),
                KnowledgeFileBlueprint(
                    file_id=f"{topic_segment}-index",
                    title=f"{topic} Index",
                    module_id="core_topics",
                    module_label="Core Topics",
                    doc_role="topic_index",
                    relative_path=f"02_core_topics/{topic_segment}/index.md",
                    subdomain=topic,
                    doc_type="note",
                    owner_engine_candidates=["InsightEngine"],
                    completion_requirements={"required": True, "required_query_tasks": 0},
                ),
            ]
        )
        for filename, title_suffix, doc_role, owners, required in TOPIC_FILE_TEMPLATES:
            items.append(
                KnowledgeFileBlueprint(
                    file_id=f"{topic_segment}-{filename[:-3]}",
                    title=f"{topic} {title_suffix}",
                    module_id="core_topics",
                    module_label="Core Topics",
                    doc_role=doc_role,
                    relative_path=f"02_core_topics/{topic_segment}/{filename}",
                    subdomain=topic,
                    doc_type="article",
                    owner_engine_candidates=owners,
                    completion_requirements={"required": required, "required_query_tasks": 0},
                )
            )
    return [item.to_dict() for item in items]


def build_required_file_paths(domain: str, blueprint: list[dict[str, object]]) -> list[str]:
    domain_segment = sanitize_path_segment(domain, "domain")
    required: list[str] = []
    for item in blueprint:
        requirements = item.get("completion_requirements", {})
        if isinstance(requirements, dict) and requirements.get("required"):
            required.append(str(Path("save") / domain_segment / str(item.get("relative_path", ""))))
    return required


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
        return (domain_dir / "02_core_topics" / sanitize_path_segment(subdomain or "topic", "topic") / "README.md").as_posix()
    if doc_role == "topic_index":
        return (domain_dir / "02_core_topics" / sanitize_path_segment(subdomain or "topic", "topic") / "index.md").as_posix()
    target_dir = domain_dir / module_directory(module_id)
    if subdomain:
        target_dir = target_dir / sanitize_path_segment(subdomain, "topic")
    filename = f"{slugify_filename(title, suffix)}.md"
    return (target_dir / filename).as_posix()


def module_labels_by_id() -> dict[str, str]:
    return {module.module_id: module.label for module in DEFAULT_KNOWLEDGE_MODULES}
