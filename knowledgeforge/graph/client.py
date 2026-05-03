from __future__ import annotations

from contextlib import suppress
from typing import Any

from neo4j import GraphDatabase

from knowledgeforge.config import Neo4jConfig


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
                is_generated=bool(node.get("is_generated", False)) or generation_state in {"documented", "link_querying", "link_verified", "approved"},
                is_completed=bool(node.get("is_completed", False)) or generation_state in {"documented", "link_verified", "approved"},
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
    ) -> None:
        tx.run(
            """
            MATCH (:Domain {id: $domain})-[:HAS_STRUCTURE_NODE]->(n:KnowledgeStructureNode {id: $node_id})
            SET n.generation_state = $generation_state,
                n.is_generated = $generation_state IN ['documented', 'link_querying', 'link_verified', 'approved'],
                n.is_completed = $generation_state IN ['documented', 'link_verified', 'approved'],
                n.generated_path = CASE WHEN $generated_path <> '' THEN $generated_path ELSE n.generated_path END,
                n.pending_task_count = coalesce($pending_task_count, n.pending_task_count, 0),
                n.completed_task_count = coalesce($completed_task_count, n.completed_task_count, 0),
                n.task_id = $task_id,
                n.domain = $domain,
                n.updated_at = datetime(),
                n.completed_at = CASE WHEN $generation_state IN ['documented', 'link_verified', 'approved'] THEN datetime() ELSE n.completed_at END
            """,
            domain=domain,
            task_id=task_id,
            node_id=node_id,
            generation_state=generation_state,
            generated_path=generated_path,
            pending_task_count=pending_task_count,
            completed_task_count=completed_task_count,
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
