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
