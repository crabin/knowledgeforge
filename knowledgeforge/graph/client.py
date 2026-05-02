from __future__ import annotations

from contextlib import suppress
from typing import Any

from neo4j import GraphDatabase

from knowledgeforge.config import Neo4jConfig


class Neo4jGraphClient:
    def __init__(self, config: Neo4jConfig) -> None:
        self._config = config

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
