from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv


LlmProvider = Literal["openai", "deepseek", "ollama"]


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    base_url: str
    model: str
    embedding_model: str
    embedding_dimensions: int
    embedding_api_key: str
    embedding_base_url: str


@dataclass(frozen=True)
class ChromaConfig:
    path: Path
    collection_name: str
    hnsw_m: int
    hnsw_construction_ef: int
    hnsw_search_ef: int


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str


@dataclass(frozen=True)
class DatabaseConfig:
    mysql_database_url: str


@dataclass(frozen=True)
class AppConfig:
    llm_provider: LlmProvider = "openai"
    openai: OpenAIConfig = field(
        default_factory=lambda: OpenAIConfig(
            api_key="test-key",
            base_url="http://localhost:8317/v1",
            model="gpt-5.2",
            embedding_model="bge-m3:latest",
            embedding_dimensions=1024,
            embedding_api_key="test-embedding-key",
            embedding_base_url="http://localhost:11434/v1",
        )
    )
    chroma: ChromaConfig = field(
        default_factory=lambda: ChromaConfig(
            path=Path("./chroma_db"),
            collection_name="domain_knowledge",
            hnsw_m=32,
            hnsw_construction_ef=200,
            hnsw_search_ef=100,
        )
    )
    neo4j: Neo4jConfig = field(
        default_factory=lambda: Neo4jConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test-password",
        )
    )
    database: DatabaseConfig = field(
        default_factory=lambda: DatabaseConfig(
            mysql_database_url="mysql://root:password@localhost:3306/knowledgeforge",
        )
    )
    save_root: Path = Path("save")
    task_state_root: Path = Path(".knowledgeforge/tasks")
    intake_session_root: Path = Path(".knowledgeforge/intake_sessions")
    audit_root: Path = Path(".knowledgeforge/audit")
    frozen_root: Path = Path(".knowledgeforge/frozen")
    max_rounds: int = 3
    log_level: str = "INFO"
    strict_graph_sync: bool = False
    enable_live_crawlers: bool = False
    plan_llm_timeout: float = 45.0
    execution_llm_timeout: float = 5.0
    max_query_network_concurrency: int = 5

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> AppConfig:
        load_dotenv(env_file, override=False)
        return cls(
            llm_provider=_get_required("LLM_PROVIDER"),
            openai=OpenAIConfig(
                api_key=_get_required("OPENAI_API_KEY"),
                base_url=_get_required("OPENAI_BASE_URL"),
                model=_get_required("OPENAI_MODEL"),
                embedding_model=_get_required("OPENAI_EMBEDDING_MODEL"),
                embedding_dimensions=_get_int("OPENAI_EMBEDDING_DIMENSIONS", 1024),
                embedding_api_key=_get_required("OPENAI_EMBEDDING_API_KEY"),
                embedding_base_url=_get_required("OPENAI_EMBEDDING_BASE_URL"),
            ),
            chroma=ChromaConfig(
                path=Path(os.getenv("CHROMADB_PATH", "./chroma_db")),
                collection_name=os.getenv("CHROMADB_COLLECTION_NAME", "domain_knowledge"),
                hnsw_m=_get_int("CHROMADB_HNSW_M", 32),
                hnsw_construction_ef=_get_int("CHROMADB_HNSW_CONSTRUCTION_EF", 200),
                hnsw_search_ef=_get_int("CHROMADB_HNSW_SEARCH_EF", 100),
            ),
            neo4j=Neo4jConfig(
                uri=_get_required("NEO4J_URI"),
                user=_get_required("NEO4J_USER"),
                password=_get_required("NEO4J_PASSWORD"),
            ),
            database=DatabaseConfig(
                mysql_database_url=_get_required("MYSQL_DATABASE_URL"),
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            enable_live_crawlers=_get_bool("ENABLE_LIVE_CRAWLERS", True),
            plan_llm_timeout=_get_float("PLAN_LLM_TIMEOUT", 45.0),
            execution_llm_timeout=_get_float("EXECUTION_LLM_TIMEOUT", 5.0),
            max_query_network_concurrency=_get_int("MAX_QUERY_NETWORK_CONCURRENCY", 5),
        )

    def show_config_status(self) -> dict[str, Any]:
        return {
            "llm": {
                "provider": self.llm_provider,
                "chat": {
                    "configured": bool(self.openai.api_key and self.openai.base_url and self.openai.model),
                    "provider_family": "openai-compatible",
                    "model": self.openai.model,
                    "base_url": self.openai.base_url,
                    "api_key_present": bool(self.openai.api_key),
                },
                "embedding": {
                    "configured": bool(
                        self.openai.embedding_model
                        and self.openai.embedding_api_key
                        and self.openai.embedding_base_url
                    ),
                    "provider_family": "openai-compatible",
                    "model": self.openai.embedding_model,
                    "base_url": self.openai.embedding_base_url,
                    "dimensions": self.openai.embedding_dimensions,
                    "api_key_present": bool(self.openai.embedding_api_key),
                },
            },
            "storage": {
                "save_root": str(self.save_root),
                "task_state_root": str(self.task_state_root),
                "intake_session_root": str(self.intake_session_root),
                "audit_root": str(self.audit_root),
                "frozen_root": str(self.frozen_root),
            },
            "retrieval": {
                "live_crawlers_enabled": self.enable_live_crawlers,
                "query_crawler": "DomainKnowledgeCrawler" if self.enable_live_crawlers else "_NoopQueryCrawler",
                "media_crawler": "MediaPerspectiveCrawler" if self.enable_live_crawlers else "_NoopMediaCrawler",
                "chromadb_configured": bool(self.chroma.path and self.chroma.collection_name),
                "chromadb_path": str(self.chroma.path),
                "chromadb_collection": self.chroma.collection_name,
            },
            "graph": {
                "neo4j_configured": bool(self.neo4j.uri and self.neo4j.user and self.neo4j.password),
                "neo4j_uri": self.neo4j.uri,
                "neo4j_user": self.neo4j.user,
                "strict_graph_sync": self.strict_graph_sync,
            },
            "database": {
                "mysql_configured": bool(self.database.mysql_database_url),
                "mysql_database_url_present": bool(self.database.mysql_database_url),
            },
            "runtime": {
                "max_rounds": self.max_rounds,
                "log_level": self.log_level,
                "plan_llm_timeout": self.plan_llm_timeout,
                "execution_llm_timeout": self.execution_llm_timeout,
                "max_query_network_concurrency": self.max_query_network_concurrency,
            },
            "legacy": {
                "llm_provider": self.llm_provider,
                "openai_configured": bool(self.openai.api_key and self.openai.base_url and self.openai.model),
                "embedding_configured": bool(
                    self.openai.embedding_model
                    and self.openai.embedding_api_key
                    and self.openai.embedding_base_url
                ),
                "neo4j_configured": bool(self.neo4j.uri and self.neo4j.user and self.neo4j.password),
                "mysql_configured": bool(self.database.mysql_database_url),
                "chromadb_configured": bool(self.chroma.path and self.chroma.collection_name),
            },
        }


def _get_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
