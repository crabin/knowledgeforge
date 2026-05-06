from __future__ import annotations

from urllib.parse import urlparse

from knowledgeforge.agent.QueryEngine.state.state import CandidateConcept, ConceptVerification, SearchHit


BASIC_COMPONENT_INTENT_TOKENS = (
    "基本组成",
    "组成部分",
    "主要组成",
    "核心组成",
    "基本结构",
    "结构组成",
    "入门结构",
    "components",
    "main parts",
    "basic parts",
    "architecture components",
)

CORE_CONCEPT_INTENT_TOKENS = (
    "核心要点",
    "关键模块",
    "核心概念",
    "主要部分",
    "core concepts",
    "key components",
    "key points",
)

TRAINING_TOKENS = (
    "loss function",
    "损失函数",
    "backpropagation",
    "反向传播",
    "optimizer",
    "优化器",
    "gradient",
    "梯度",
    "training",
    "训练",
)

EXTENSION_TOKENS = (
    "dropout",
    "batch normalization",
    "批归一化",
    "attention",
    "注意力",
    "residual",
    "残差",
)

CONCEPT_ALIASES = {
    "input layer": ("input layer", "输入层"),
    "hidden layer": ("hidden layer", "隐藏层"),
    "output layer": ("output layer", "输出层"),
    "neuron": ("neuron", "neurons", "神经元"),
    "weight": ("weight", "weights", "权重"),
    "bias": ("bias", "biases", "偏置"),
    "activation function": ("activation function", "activation", "激活函数"),
    "loss function": ("loss function", "loss", "损失函数"),
    "backpropagation": ("backpropagation", "back propagation", "反向传播"),
    "optimizer": ("optimizer", "optimizers", "优化器"),
    "dropout": ("dropout",),
    "batch normalization": ("batch normalization", "batchnorm", "批归一化"),
    "attention": ("attention", "注意力"),
    "residual connection": ("residual connection", "residual", "残差连接", "残差"),
}

ROLE_EXPLANATIONS = {
    "input layer": "接收原始输入数据。",
    "hidden layer": "逐层提取和变换特征。",
    "output layer": "生成模型的最终预测结果。",
    "neuron": "执行加权求和和非线性变换的基本计算单元。",
    "weight": "表示不同输入信号的重要程度。",
    "bias": "为神经元输出提供可学习的偏移量。",
    "activation function": "引入非线性，使网络能学习复杂关系。",
    "loss function": "衡量预测结果与真实目标之间的差距。",
    "backpropagation": "根据误差计算参数更新方向。",
    "optimizer": "根据梯度更新权重和偏置。",
}


def classify_query_intent(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in BASIC_COMPONENT_INTENT_TOKENS):
        return "basic_components"
    if any(token in lowered for token in CORE_CONCEPT_INTENT_TOKENS):
        return "core_concepts"
    if any(token in lowered for token in ("paper", "论文", "arxiv", "benchmark")):
        return "paper"
    if any(token in lowered for token in ("model", "模型", "weights", "hugging face")):
        return "model"
    if any(token in lowered for token in ("dataset", "数据集")):
        return "dataset"
    if any(token in lowered for token in ("news", "新闻", "latest", "最新")):
        return "news"
    if any(token in lowered for token in ("security", "漏洞", "cve", "安全")):
        return "security"
    if any(token in lowered for token in ("how to", "用法", "usage", "教程")):
        return "usage"
    if any(token in lowered for token in ("definition", "定义", "是什么")):
        return "definition"
    return "general"


def build_broad_queries(*, domain: str, query: str, intent: str) -> list[str]:
    if intent not in {"basic_components", "core_concepts"}:
        return []
    topic = _compact_topic(domain=domain, query=query)
    return _dedupe(
        [
            f"basic components of {topic}",
            f"main parts of {topic}",
            f"{topic} basics",
            f"{topic} architecture components",
            f"{topic} 基本组成",
            f"{topic} 主要由什么组成",
            f"{topic} 基本结构",
            f"{topic} 结构组成",
        ]
    )


def extract_candidate_concepts(hits: list[SearchHit]) -> list[CandidateConcept]:
    by_name: dict[str, CandidateConcept] = {}
    for hit in hits:
        text = f"{hit.title} {hit.snippet} {hit.url}".lower()
        for canonical_name, aliases in CONCEPT_ALIASES.items():
            if not any(alias.lower() in text for alias in aliases):
                continue
            concept = by_name.setdefault(
                canonical_name,
                CandidateConcept(
                    name=canonical_name,
                    canonical_name=canonical_name,
                    preliminary_category=_concept_category(canonical_name),
                ),
            )
            concept.mentions += 1
            if hit.url and hit.url not in concept.source_urls:
                concept.source_urls.append(hit.url)
            if hit.source_type and hit.source_type not in concept.source_types:
                concept.source_types.append(hit.source_type)
    return sorted(by_name.values(), key=lambda item: (-item.mentions, item.canonical_name))


def build_verification_queries(*, domain: str, query: str, concepts: list[CandidateConcept]) -> list[str]:
    topic = _compact_topic(domain=domain, query=query)
    queries: list[str] = []
    for concept in concepts[:10]:
        queries.extend(
            [
                f"{topic} {concept.canonical_name} explained",
                f"is {concept.canonical_name} a core component of {topic}",
            ]
        )
    if concepts:
        queries.extend(
            [
                f"{topic} components vs training process",
                f"{topic} core components reliable sources",
            ]
        )
    return _dedupe(queries)


def classify_verified_concepts(concepts: list[CandidateConcept], hits: list[SearchHit]) -> list[ConceptVerification]:
    matrix: list[ConceptVerification] = []
    for concept in concepts:
        matching_hits = [_hit for _hit in hits if _concept_in_hit(concept, _hit)]
        support_count = len({hit.url for hit in matching_hits if hit.url})
        reliable_support_count = len(
            {
                hit.url
                for hit in matching_hits
                if hit.url and _is_reliable_hit(hit)
            }
        )
        category = _concept_category(concept.canonical_name)
        included = category != "excluded_extension" and (reliable_support_count >= 1 or support_count >= 2)
        reason = _verification_reason(
            category=category,
            support_count=support_count,
            reliable_support_count=reliable_support_count,
            included=included,
        )
        matrix.append(
            ConceptVerification(
                canonical_name=concept.canonical_name,
                support_count=support_count,
                reliable_support_count=reliable_support_count,
                category=category,
                included=included,
                reason=reason,
                one_sentence_role=ROLE_EXPLANATIONS.get(concept.canonical_name, "用于支撑该主题的基础理解。"),
            )
        )
    return sorted(matrix, key=lambda item: (not item.included, item.category, item.canonical_name))


def useful_information_checks(matrix: list[ConceptVerification]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for item in matrix:
        checks.append(
            {
                "concept": item.canonical_name,
                "directly_answers_question": item.category != "excluded_extension",
                "reliable_source": item.reliable_support_count >= 1,
                "multi_source_verified": item.support_count >= 2,
                "basic_not_extension": item.category != "excluded_extension",
                "one_sentence_explainable": bool(item.one_sentence_role),
                "included": item.included,
            }
        )
    return checks


def build_structured_sections(matrix: list[ConceptVerification]) -> list[dict[str, object]]:
    labels = {
        "core_structure": "结构组成",
        "training_process": "训练组成",
        "core_content": "核心内容",
    }
    sections: list[dict[str, object]] = []
    for category, title in labels.items():
        items = [
            {"name": item.canonical_name, "role": item.one_sentence_role}
            for item in matrix
            if item.included and item.category == category
        ]
        if items:
            sections.append({"title": title, "items": items})
    return sections


def build_short_summary(matrix: list[ConceptVerification]) -> str:
    core = [item.canonical_name for item in matrix if item.included and item.category == "core_structure"]
    training = [item.canonical_name for item in matrix if item.included and item.category == "training_process"]
    if core and training:
        return (
            "如果只谈网络本身，核心包括"
            + "、".join(core)
            + "；如果谈完整训练过程，还需要"
            + "、".join(training)
            + "。"
        )
    included = [item.canonical_name for item in matrix if item.included]
    if included:
        return "当前问题的核心要点包括：" + "、".join(included) + "。"
    return ""


def source_cross_check(hits: list[SearchHit], limit: int = 3) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for hit in sorted(hits, key=lambda item: item.score, reverse=True):
        if not hit.url or hit.url in seen or not _is_reliable_hit(hit):
            continue
        seen.add(hit.url)
        rows.append(
            {
                "title": hit.title,
                "url": hit.url,
                "publisher": urlparse(hit.url).netloc or "unknown",
                "source_type": hit.source_type,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _compact_topic(*, domain: str, query: str) -> str:
    compact = " ".join(query.split())
    if domain and domain.lower() not in compact.lower():
        compact = f"{domain} {compact}".strip()
    return compact


def _concept_category(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in EXTENSION_TOKENS):
        return "excluded_extension"
    if any(token in lowered for token in TRAINING_TOKENS):
        return "training_process"
    if lowered in {"input layer", "hidden layer", "output layer", "neuron", "weight", "bias", "activation function"}:
        return "core_structure"
    return "core_content"


def _concept_in_hit(concept: CandidateConcept, hit: SearchHit) -> bool:
    text = f"{hit.title} {hit.snippet} {hit.url}".lower()
    aliases = CONCEPT_ALIASES.get(concept.canonical_name, (concept.canonical_name,))
    return any(alias.lower() in text for alias in aliases)


def _is_reliable_hit(hit: SearchHit) -> bool:
    netloc = urlparse(hit.url).netloc.lower()
    if hit.source_type == "official":
        return True
    return any(
        domain in netloc
        for domain in (
            "wikipedia.org",
            "arxiv.org",
            "deeplearningbook.org",
            "stanford.edu",
            "mit.edu",
            "ibm.com",
            "google.com",
            "tensorflow.org",
            "pytorch.org",
        )
    )


def _verification_reason(*, category: str, support_count: int, reliable_support_count: int, included: bool) -> str:
    if category == "excluded_extension":
        return "属于进阶扩展项，不纳入基础组成。"
    if included:
        return f"被 {support_count} 个来源提到，其中 {reliable_support_count} 个为可靠来源。"
    return f"支持来源不足：共 {support_count} 个来源，其中可靠来源 {reliable_support_count} 个。"


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = " ".join(item.split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped
