from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ArticleMeta:
    article_id: str
    title: str
    source_path: str
    source_rel_path: str
    file_type: str
    content_hash: str
    modified_time: datetime
    created_at: datetime
    updated_at: datetime


@dataclass
class ChunkMeta:
    chunk_id: str
    article_id: str
    chunk_index: int
    nearest_heading: str
    text: str
    source_rel_path: str
    title: str
    content_hash: str
    embedding_model: str
    embedding_dimension: int


@dataclass
class ParsedArticle:
    title: str
    source_path: str
    source_rel_path: str
    file_type: str
    content_hash: str
    modified_time: datetime
    body: str


@dataclass
class IndexManifest:
    schema_version: int = 1
    source_root: str = ""
    vector_store: str = "qdrant"
    keyword_store: str = "elasticsearch"
    retrieval_mode: str = "hybrid_rrf"
    vector_distance_metric: str = "cosine"
    embedding_provider: str = "openai-compatible"
    embedding_model: str = ""
    embedding_dimension: int = 0
    qdrant_collection: str = ""
    elasticsearch_index: str = ""
    chunker_config: dict[str, Any] = field(default_factory=dict)
    articles: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunk: ChunkMeta
    similarity: float
    sources: list[str] = field(default_factory=list)


@dataclass
class ChatResponse:
    answer: str
    citations: list[str]
    retrieved_count: int
    intent: str = "rag_query"
