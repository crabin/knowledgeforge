from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from neo4j import GraphDatabase

from knowledgeforge.config import Neo4jConfig


def _neo4j_safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        if isinstance(value, list):
            if all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                safe[key] = value
            else:
                safe[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, dict):
            safe[key] = json.dumps(value, ensure_ascii=False)
        else:
            safe[key] = value
    return safe


class Neo4jGraphClient:
    def __init__(self, config: Neo4jConfig) -> None:
        self._config = config

    def snapshot_domain_graph(
        self,
        *,
        domain: str,
        node_limit: int = 300,
        relationship_limit: int = 600,
    ) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_read(
                    self._read_domain_graph,
                    domain,
                    node_limit,
                    relationship_limit,
                )
        finally:
            with suppress(Exception):
                driver.close()

    def sync_document(
        self,
        *,
        domain: str,
        subdomain: str,
        article_id: str,
        article_path: str,
        entities: list[dict[str, Any]],
        structure_graph: dict[str, Any] | None = None,
    ) -> None:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                session.execute_write(
                    self._write_graph,
                    domain,
                    subdomain,
                    article_id,
                    article_path,
                    entities,
                    structure_graph or {},
                )
        finally:
            with suppress(Exception):
                driver.close()

    def sync_structure_graph(
        self,
        *,
        domain: str,
        task_id: str,
        structure_graph: dict[str, Any],
    ) -> None:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                session.execute_write(self._write_structure_graph, domain, task_id, structure_graph)
        finally:
            with suppress(Exception):
                driver.close()

    def structure_review_context(
        self,
        *,
        domain: str,
        task_id: str,
        knowledge_id: str,
        node_limit: int = 80,
        relationship_limit: int = 160,
    ) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_read(
                    self._read_structure_review_context,
                    domain,
                    task_id,
                    knowledge_id,
                    node_limit,
                    relationship_limit,
                )
        finally:
            with suppress(Exception):
                driver.close()

    def inspect_domain_graph_issues(self, *, domain: str, task_id: str) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_read(self._read_domain_graph_issues, domain, task_id)
        finally:
            with suppress(Exception):
                driver.close()

    def delete_domain_graph_issue_node(self, *, domain: str, task_id: str, graph_id: str) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_write(self._delete_domain_graph_issue_node, domain, task_id, graph_id)
        finally:
            with suppress(Exception):
                driver.close()

    def link_domain_graph_issue_node(
        self,
        *,
        domain: str,
        task_id: str,
        graph_id: str,
        target_node_id: str,
        relationship_type: str = "RELATED_TO",
    ) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_write(
                    self._link_domain_graph_issue_node,
                    domain,
                    task_id,
                    graph_id,
                    target_node_id,
                    relationship_type,
                )
        finally:
            with suppress(Exception):
                driver.close()

    def mark_structure_node_generated(
        self,
        *,
        domain: str,
        task_id: str,
        node_id: str,
        generated_path: str,
    ) -> None:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                session.execute_write(
                    self._write_structure_node_generated,
                    domain,
                    task_id,
                    node_id,
                    generated_path,
                )
        finally:
            with suppress(Exception):
                driver.close()

    def update_structure_node_status(
        self,
        *,
        domain: str,
        task_id: str,
        node_id: str,
        generation_state: str,
        generated_path: str = "",
        pending_task_count: int | None = None,
        completed_task_count: int | None = None,
        extra_properties: dict[str, Any] | None = None,
    ) -> None:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                session.execute_write(
                    self._write_structure_node_status,
                    domain,
                    task_id,
                    node_id,
                    generation_state,
                    generated_path,
                    pending_task_count,
                    completed_task_count,
                    _neo4j_safe_properties(extra_properties or {}),
                )
        finally:
            with suppress(Exception):
                driver.close()

    def clear_knowledgeforge_graph(self) -> dict[str, Any]:
        driver = GraphDatabase.driver(
            self._config.uri,
            auth=(self._config.user, self._config.password),
            connection_timeout=1.0,
            max_transaction_retry_time=0,
        )
        try:
            with driver.session() as session:
                return session.execute_write(self._delete_knowledgeforge_graph)
        finally:
            with suppress(Exception):
                driver.close()

    @staticmethod
    def _write_graph(
        tx: Any,
        domain: str,
        subdomain: str,
        article_id: str,
        article_path: str,
        entities: list[dict[str, Any]],
        structure_graph: dict[str, Any],
    ) -> None:
        tx.run(
            """
            MERGE (d:Domain {id: $domain})
            MERGE (s:SubTopic {id: $subdomain})
            MERGE (a:Article {id: $article_id})
            SET a.path = $article_path
            MERGE (d)-[:HAS_SUBTOPIC]->(s)
            MERGE (s)-[:HAS_ARTICLE]->(a)
            """,
            domain=domain,
            subdomain=subdomain,
            article_id=article_id,
            article_path=article_path,
        )
        for entity in entities:
            tx.run(
                """
                MERGE (e:Entity {id: $entity_id})
                SET e.type = $entity_type
                MERGE (a:Article {id: $article_id})
                MERGE (a)-[:MENTIONS]->(e)
                """,
                entity_id=entity["name"],
                entity_type=entity["type"],
                article_id=article_id,
            )
        for node in structure_graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            tx.run(
                """
                MERGE (n:KnowledgeStructureNode {id: $node_id})
                SET n.title = $title,
                    n.node_type = $node_type,
                    n.path = $path,
                    n.doc_type = $doc_type
                WITH n
                MATCH (d:Domain {id: $domain})
                MERGE (d)-[:HAS_STRUCTURE_NODE]->(n)
                """,
                domain=domain,
                node_id=str(node.get("node_id", "")),
                title=str(node.get("title", "")),
                node_type=str(node.get("node_type", "")),
                path=str(node.get("relative_path", "")),
                doc_type=str(node.get("doc_type", "")),
            )
        for edge in structure_graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            tx.run(
                """
                MERGE (from_node:KnowledgeStructureNode {id: $from_node_id})
                MERGE (to_node:KnowledgeStructureNode {id: $to_node_id})
                MERGE (from_node)-[r:STRUCTURE_EDGE {type: $edge_type}]->(to_node)
                """,
                from_node_id=str(edge.get("from_node_id", "")),
                to_node_id=str(edge.get("to_node_id", "")),
                edge_type=str(edge.get("edge_type", "CONTAINS")),
            )

    @staticmethod
    def _write_structure_graph(tx: Any, domain: str, task_id: str, structure_graph: dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (d:Domain {id: $domain})
            SET d.task_id = $task_id
            """,
            domain=domain,
            task_id=task_id,
        )
        for node in structure_graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("node_id", ""))
            if not node_id:
                continue
            generation_state = str(node.get("generation_state", "planned") or "planned")
            tx.run(
                """
                MATCH (d:Domain {id: $domain})
                MERGE (n:KnowledgeStructureNode {id: $node_id})
                SET n.title = $title,
                    n.node_type = $node_type,
                    n.path = $path,
                    n.doc_type = $doc_type,
                    n.parent_node_id = $parent_node_id,
                    n.task_id = $task_id,
                    n.domain = $domain,
                    n.is_generated = $is_generated,
                    n.is_completed = $is_completed,
                    n.generation_state = $generation_state,
                    n.suggested_relative_path = $suggested_relative_path,
                    n.document_completion_status = $document_completion_status,
                    n.review_status = $review_status,
                    n.pending_task_count = $pending_task_count,
                    n.completed_task_count = $completed_task_count,
                    n.updated_at = $updated_at
                MERGE (d)-[:HAS_STRUCTURE_NODE]->(n)
                """,
                domain=domain,
                task_id=task_id,
                node_id=node_id,
                title=str(node.get("title", "")),
                node_type=str(node.get("node_type", "")),
                path=str(node.get("relative_path", "")),
                doc_type=str(node.get("doc_type", "")),
                parent_node_id=str(node.get("parent_node_id", "")),
                generation_state=generation_state,
                is_generated=bool(node.get("is_generated", False)) or generation_state in {"completion_ready", "document_generating", "documented", "link_querying", "link_verified", "approved"},
                is_completed=bool(node.get("is_completed", False)) or generation_state in {"completion_ready", "documented", "link_verified", "approved"},
                suggested_relative_path=str(node.get("suggested_relative_path", node.get("relative_path", ""))),
                document_completion_status=str(node.get("document_completion_status", "not_requested")),
                review_status=str(node.get("review_status", "")),
                pending_task_count=int(node.get("pending_task_count", 0) or 0),
                completed_task_count=int(node.get("completed_task_count", 0) or 0),
                updated_at=str(structure_graph.get("generated_at", "")),
            )
        for edge in structure_graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            from_node_id = str(edge.get("from_node_id", ""))
            to_node_id = str(edge.get("to_node_id", ""))
            if not from_node_id or not to_node_id:
                continue
            tx.run(
                """
                MERGE (from_node:KnowledgeStructureNode {id: $from_node_id})
                MERGE (to_node:KnowledgeStructureNode {id: $to_node_id})
                MERGE (from_node)-[r:STRUCTURE_EDGE {type: $edge_type}]->(to_node)
                SET r.task_id = $task_id,
                    r.domain = $domain
                """,
                domain=domain,
                task_id=task_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                edge_type=str(edge.get("edge_type", "CONTAINS")),
            )

    @staticmethod
    def _write_structure_node_generated(
        tx: Any,
        domain: str,
        task_id: str,
        node_id: str,
        generated_path: str,
    ) -> None:
        tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(n:KnowledgeStructureNode {id: $node_id})
            SET n.is_generated = true,
                n.generation_state = 'documented',
                n.generated_path = $generated_path,
                n.document_completion_status = 'generated',
                n.task_id = $task_id,
                n.generated_at = datetime()
            """,
            domain=domain,
            task_id=task_id,
            node_id=node_id,
            generated_path=generated_path,
        )

    @staticmethod
    def _write_structure_node_status(
        tx: Any,
        domain: str,
        task_id: str,
        node_id: str,
        generation_state: str,
        generated_path: str,
        pending_task_count: int | None,
        completed_task_count: int | None,
        extra_properties: dict[str, Any],
    ) -> None:
        tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(n:KnowledgeStructureNode {id: $node_id})
            SET n.generation_state = $generation_state,
                n.is_generated = $generation_state IN ['completion_ready', 'document_generating', 'documented', 'link_querying', 'link_verified', 'approved'],
                n.is_completed = $generation_state IN ['completion_ready', 'documented', 'link_verified', 'approved'],
                n.generated_path = CASE WHEN $generated_path <> '' THEN $generated_path ELSE n.generated_path END,
                n.suggested_relative_path = coalesce($extra_properties.suggested_relative_path, n.suggested_relative_path),
                n.document_completion_status = coalesce($extra_properties.document_completion_status, n.document_completion_status),
                n.review_status = coalesce($extra_properties.review_status, n.review_status),
                n.repair_log = coalesce($extra_properties.repair_log, n.repair_log),
                n.evidence_links = coalesce($extra_properties.evidence_links, n.evidence_links, []),
                n.selected_link = coalesce($extra_properties.selected_link, n.selected_link),
                n.source_kind = coalesce($extra_properties.source_kind, n.source_kind),
                n.reachable = coalesce($extra_properties.reachable, n.reachable),
                n.relevance_reason = coalesce($extra_properties.relevance_reason, n.relevance_reason),
                n.checked_at = coalesce($extra_properties.checked_at, n.checked_at),
                n.claim_or_gap = coalesce($extra_properties.claim_or_gap, n.claim_or_gap),
                n.expected_evidence = coalesce($extra_properties.expected_evidence, n.expected_evidence, []),
                n.pending_task_count = coalesce($pending_task_count, n.pending_task_count, 0),
                n.completed_task_count = coalesce($completed_task_count, n.completed_task_count, 0),
                n.task_id = $task_id,
                n.domain = $domain,
                n.updated_at = datetime(),
                n.completed_at = CASE WHEN $generation_state IN ['completion_ready', 'documented', 'link_verified', 'approved'] THEN datetime() ELSE n.completed_at END
            """,
            domain=domain,
            task_id=task_id,
            node_id=node_id,
            generation_state=generation_state,
            generated_path=generated_path,
            pending_task_count=pending_task_count,
            completed_task_count=completed_task_count,
            extra_properties=extra_properties,
        )

    @staticmethod
    def _delete_knowledgeforge_graph(tx: Any) -> dict[str, Any]:
        labels = [
            "Domain",
            "SubTopic",
            "Article",
            "Source",
            "KnowledgePoint",
            "KnowledgeStructureNode",
            "KnowledgeIndex",
            "KnowledgeSection",
        ]
        relationships = tx.run(
            """
            MATCH (n)
            WHERE any(label IN labels(n) WHERE label IN $labels)
            OPTIONAL MATCH (article:Article)-[:MENTIONS]->(entity:Entity)
            WITH collect(DISTINCT n) + collect(DISTINCT entity) AS raw_nodes
            UNWIND raw_nodes AS app_node
            WITH DISTINCT app_node
            WHERE app_node IS NOT NULL
            MATCH (app_node)-[r]-()
            RETURN count(DISTINCT r) AS count
            """,
            labels=labels,
        ).single()
        relationship_count = int(relationships["count"] if relationships else 0)
        deleted_nodes = 0
        while True:
            record = tx.run(
                """
                MATCH (n)
                WHERE any(label IN labels(n) WHERE label IN $labels)
                OPTIONAL MATCH (article:Article)-[:MENTIONS]->(entity:Entity)
                WITH collect(DISTINCT n) + collect(DISTINCT entity) AS raw_nodes
                UNWIND raw_nodes AS app_node
                WITH DISTINCT app_node
                WHERE app_node IS NOT NULL
                WITH app_node LIMIT 1000
                DETACH DELETE app_node
                RETURN count(app_node) AS count
                """,
                labels=labels,
            ).single()
            count = int(record["count"] if record else 0)
            deleted_nodes += count
            if count == 0:
                break
        return {
            "status": "cleared",
            "labels": labels,
            "deleted_nodes": deleted_nodes,
            "deleted_relationships": relationship_count,
        }

    @staticmethod
    def _read_domain_graph(
        tx: Any,
        domain: str,
        node_limit: int,
        relationship_limit: int,
    ) -> dict[str, Any]:
        node_rows = tx.run(
            """
            MATCH (d:Domain {id: $domain})
            OPTIONAL MATCH (d)-[:HAS_SUBTOPIC]->(s:SubTopic)
            OPTIONAL MATCH (s)-[:HAS_ARTICLE]->(a:Article)
            OPTIONAL MATCH (a)-[:MENTIONS]->(e:Entity)
            OPTIONAL MATCH (d)-[:HAS_STRUCTURE_NODE]->(ks:KnowledgeStructureNode)
            WITH collect(d) + collect(s) + collect(a) + collect(e) + collect(ks) AS raw_nodes
            UNWIND raw_nodes AS node
            WITH DISTINCT node
            WHERE node IS NOT NULL
            RETURN elementId(node) AS graph_id, labels(node) AS labels, properties(node) AS properties
            LIMIT $node_limit
            """,
            domain=domain,
            node_limit=node_limit,
        )
        nodes = [_normalize_node_row(row) for row in node_rows]
        visible_node_ids = {node["id"] for node in nodes}

        relationship_rows = tx.run(
            """
            MATCH (d:Domain {id: $domain})-[r:HAS_SUBTOPIC]->(s:SubTopic)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            UNION
            MATCH (:Domain {id: $domain})-[:HAS_SUBTOPIC]->(s:SubTopic)-[r:HAS_ARTICLE]->(a:Article)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            UNION
            MATCH (:Domain {id: $domain})-[:HAS_SUBTOPIC]->(:SubTopic)-[:HAS_ARTICLE]->(a:Article)-[r:MENTIONS]->(e:Entity)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            UNION
            MATCH (d:Domain {id: $domain})-[r:HAS_STRUCTURE_NODE]->(ks:KnowledgeStructureNode)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            UNION
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(from_node:KnowledgeStructureNode)-[r:STRUCTURE_EDGE]->(to_node:KnowledgeStructureNode)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            UNION
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(ks:KnowledgeStructureNode)<-[r:RELATED_TO]-(n)
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            LIMIT $relationship_limit
            """,
            domain=domain,
            relationship_limit=relationship_limit,
        )
        edges = [
            _normalize_relationship_row(row)
            for row in relationship_rows
            if row["source"] in visible_node_ids and row["target"] in visible_node_ids
        ]
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _read_domain_graph_issues(tx: Any, domain: str, task_id: str) -> dict[str, Any]:
        rows = tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(ks:KnowledgeStructureNode)
            MATCH (n)
            WHERE NOT n:KnowledgeStructureNode
              AND (
                coalesce(n.id, '') = coalesce(ks.title, '')
                OR coalesce(n.name, '') = coalesce(ks.title, '')
                OR coalesce(n.title, '') = coalesce(ks.title, '')
                OR coalesce(n.id, '') = coalesce(ks.id, '')
              )
              AND (n:Entity OR n:SubTopic OR n:Article)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, ks, count(DISTINCT r) AS relationship_count, collect(DISTINCT type(r)) AS relationship_types
            RETURN elementId(n) AS graph_id,
                   labels(n) AS labels,
                   properties(n) AS properties,
                   relationship_count,
                   relationship_types,
                   ks.id AS matching_structure_node_id,
                   ks.title AS matching_structure_title,
                   ks.node_type AS matching_structure_type,
                   ks.suggested_relative_path AS matching_structure_path
            ORDER BY relationship_count ASC, matching_structure_title ASC
            LIMIT 100
            """,
            domain=domain,
            task_id=task_id,
        )
        issues_by_graph_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            properties = _json_safe_properties(dict(row["properties"] or {}))
            labels = list(row["labels"] or [])
            graph_id = str(row["graph_id"])
            relationship_types = sorted({str(item) for item in row["relationship_types"] or [] if item})
            current_match = {
                "matching_structure_node_id": str(row["matching_structure_node_id"] or ""),
                "matching_structure_title": str(row["matching_structure_title"] or ""),
                "matching_structure_type": str(row["matching_structure_type"] or ""),
                "matching_structure_path": str(row["matching_structure_path"] or ""),
            }
            issue = issues_by_graph_id.get(graph_id)
            if issue is None:
                issue = {
                    "graph_id": graph_id,
                    "labels": labels,
                    "type": _node_type(labels, properties),
                    "logical_id": str(properties.get("id") or properties.get("name") or properties.get("title") or ""),
                    "title": str(properties.get("title") or properties.get("name") or properties.get("id") or row["graph_id"]),
                    "path": str(properties.get("path", "")),
                    "relationship_count": int(row["relationship_count"] or 0),
                    "relationship_types": relationship_types,
                    "reason": "duplicate_non_structure_knowledge_point",
                    **current_match,
                    "matching_candidates": [current_match] if any(current_match.values()) else [],
                    "recommended_action": "delete_or_link",
                }
                issues_by_graph_id[graph_id] = issue
                continue
            issue["relationship_count"] = min(int(issue["relationship_count"]), int(row["relationship_count"] or 0))
            issue["relationship_types"] = sorted(set(issue["relationship_types"]) | set(relationship_types))
            candidates = issue.setdefault("matching_candidates", [])
            if any(current_match.values()) and current_match not in candidates:
                candidates.append(current_match)
                current_best = (
                    str(issue.get("matching_structure_title") or ""),
                    str(issue.get("matching_structure_type") or ""),
                    str(issue.get("matching_structure_node_id") or ""),
                )
                candidate_key = (
                    current_match["matching_structure_title"],
                    current_match["matching_structure_type"],
                    current_match["matching_structure_node_id"],
                )
                if candidate_key < current_best:
                    issue.update(current_match)
        issues = sorted(
            issues_by_graph_id.values(),
            key=lambda item: (
                int(item.get("relationship_count", 0)),
                str(item.get("title", "")),
                str(item.get("graph_id", "")),
            ),
        )
        return {"issues": issues, "count": len(issues)}

    @staticmethod
    def _delete_domain_graph_issue_node(tx: Any, domain: str, task_id: str, graph_id: str) -> dict[str, Any]:
        record = tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(ks:KnowledgeStructureNode)
            MATCH (n)
            WHERE elementId(n) = $graph_id
              AND NOT n:KnowledgeStructureNode
              AND (
                coalesce(n.id, '') = coalesce(ks.title, '')
                OR coalesce(n.name, '') = coalesce(ks.title, '')
                OR coalesce(n.title, '') = coalesce(ks.title, '')
                OR coalesce(n.id, '') = coalesce(ks.id, '')
              )
              AND (n:Entity OR n:SubTopic OR n:Article)
            OPTIONAL MATCH (n)-[r]-()
            WITH n, collect(DISTINCT r) AS rels
            DETACH DELETE n
            RETURN 1 AS deleted_nodes, size(rels) AS deleted_relationships
            """,
            domain=domain,
            task_id=task_id,
            graph_id=graph_id,
        ).single()
        return {
            "status": "deleted" if record else "not_found",
            "graph_id": graph_id,
            "deleted_nodes": int(record["deleted_nodes"] if record else 0),
            "deleted_relationships": int(record["deleted_relationships"] if record else 0),
        }

    @staticmethod
    def _link_domain_graph_issue_node(
        tx: Any,
        domain: str,
        task_id: str,
        graph_id: str,
        target_node_id: str,
        relationship_type: str,
    ) -> dict[str, Any]:
        safe_type = relationship_type if relationship_type in {"RELATED_TO", "MENTIONS", "ALIGNED_WITH"} else "RELATED_TO"
        record = tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(target:KnowledgeStructureNode {id: $target_node_id})
            MATCH (n)
            WHERE elementId(n) = $graph_id
              AND NOT n:KnowledgeStructureNode
            MERGE (n)-[r:RELATED_TO]->(target)
            SET r.type = $relationship_type,
                r.domain = $domain,
                r.task_id = $task_id,
                r.created_at = datetime()
            RETURN elementId(r) AS relationship_graph_id,
                   elementId(n) AS source_graph_id,
                   target.id AS target_node_id,
                   target.title AS target_title
            """,
            domain=domain,
            task_id=task_id,
            graph_id=graph_id,
            target_node_id=target_node_id,
            relationship_type=safe_type,
        ).single()
        if record is None:
            return {"status": "not_found", "graph_id": graph_id, "target_node_id": target_node_id}
        return {
            "status": "linked",
            "graph_id": str(record["source_graph_id"]),
            "target_node_id": str(record["target_node_id"]),
            "target_title": str(record["target_title"] or ""),
            "relationship_graph_id": str(record["relationship_graph_id"]),
            "relationship_type": safe_type,
        }

    @staticmethod
    def _read_structure_review_context(
        tx: Any,
        domain: str,
        task_id: str,
        knowledge_id: str,
        node_limit: int,
        relationship_limit: int,
    ) -> dict[str, Any]:
        node_rows = tx.run(
            """
            MATCH (d:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(current:KnowledgeStructureNode {id: $knowledge_id})
            WHERE current.task_id = $task_id OR current.task_id IS NULL
            OPTIONAL MATCH (current)-[:STRUCTURE_EDGE]-(neighbor:KnowledgeStructureNode)
            WITH collect(DISTINCT current) + collect(DISTINCT neighbor) AS raw_nodes
            UNWIND raw_nodes AS node
            WITH DISTINCT node
            WHERE node IS NOT NULL
            RETURN elementId(node) AS graph_id, labels(node) AS labels, properties(node) AS properties
            LIMIT $node_limit
            """,
            domain=domain,
            task_id=task_id,
            knowledge_id=knowledge_id,
            node_limit=node_limit,
        )
        nodes = [_normalize_node_row(row) for row in node_rows]
        visible_node_ids = {node["id"] for node in nodes}
        if not visible_node_ids:
            return {"nodes": [], "edges": []}

        relationship_rows = tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(current:KnowledgeStructureNode {id: $knowledge_id})-[r:STRUCTURE_EDGE]-(neighbor:KnowledgeStructureNode)
            WHERE current.task_id = $task_id OR current.task_id IS NULL
            RETURN elementId(r) AS graph_id,
                   elementId(startNode(r)) AS source,
                   elementId(endNode(r)) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            LIMIT $relationship_limit
            """,
            domain=domain,
            task_id=task_id,
            knowledge_id=knowledge_id,
            relationship_limit=relationship_limit,
        )
        edges = [
            _normalize_relationship_row(row)
            for row in relationship_rows
            if row["source"] in visible_node_ids and row["target"] in visible_node_ids
        ]
        return {"nodes": nodes, "edges": edges}


def _normalize_node_row(row: Any) -> dict[str, Any]:
    labels = list(row["labels"] or [])
    properties = _json_safe_properties(dict(row["properties"] or {}))
    node_type = _node_type(labels, properties)
    title = str(
        properties.get("title")
        or properties.get("label_text")
        or properties.get("name")
        or properties.get("id")
        or row["graph_id"]
    )
    return {
        "id": str(row["graph_id"]),
        "title": title,
        "type": node_type,
        "labels": labels,
        "path": str(properties.get("path", "")),
        "properties": properties,
    }


def _normalize_relationship_row(row: Any) -> dict[str, Any]:
    properties = _json_safe_properties(dict(row["properties"] or {}))
    edge_type = str(row["type"])
    return {
        "id": str(row["graph_id"]),
        "source": str(row["source"]),
        "target": str(row["target"]),
        "type": edge_type,
        "properties": properties,
    }


def _node_type(labels: list[str], properties: dict[str, Any]) -> str:
    priority = ["Domain", "SubTopic", "Article", "Entity", "KnowledgeStructureNode"]
    for label in priority:
        if label in labels:
            if label == "Entity" and properties.get("type"):
                return str(properties["type"])
            return label
    return labels[0] if labels else "Node"


def _json_safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in properties.items()}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return _json_safe_properties(value)
    return str(value)
