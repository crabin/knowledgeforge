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


def _normalize_node_row(row: Any) -> dict[str, Any]:
    labels = list(row["labels"] or [])
    properties = dict(row["properties"] or {})
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
    properties = dict(row["properties"] or {})
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
