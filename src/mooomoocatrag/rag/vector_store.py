from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from types import SimpleNamespace
from typing import Protocol

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest

try:
    from elasticsearch import Elasticsearch, helpers
except ImportError:  # pragma: no cover - exercised after dependency install
    Elasticsearch = None

    class _Helpers:
        @staticmethod
        def bulk(*args, **kwargs):
            raise RuntimeError(
                "elasticsearch package is not installed. Run: python -m pip install -e '.[dev]'"
            )

    helpers = _Helpers()

try:
    from qdrant_client import QdrantClient, models as qdrant_models
except ImportError:  # pragma: no cover - exercised after dependency install
    QdrantClient = None

    class _Distance:
        COSINE = "cosine"

    class _VectorParams:
        def __init__(self, size: int, distance):
            self.size = size
            self.distance = distance

    class _PointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class _PointIdsList:
        def __init__(self, points):
            self.points = points

    qdrant_models = SimpleNamespace(
        Distance=_Distance,
        VectorParams=_VectorParams,
        PointStruct=_PointStruct,
        PointIdsList=_PointIdsList,
    )


def _require_dependency(name: str, dependency) -> None:
    if dependency is None:
        raise RuntimeError(
            f"{name} package is not installed. Run: python -m pip install -e '.[dev]'"
        )


class DenseStore(Protocol):
    def upsert_chunks(self, chunks: list[ChunkMeta], vectors: list[list[float]]) -> None: ...
    def delete_chunks(self, chunk_ids: list[str]) -> None: ...
    def query_dense(self, query_vector: list[float], top_k: int) -> list[dict]: ...
    def clear(self) -> None: ...


class KeywordStore(Protocol):
    def upsert_chunks(self, chunks: list[ChunkMeta]) -> None: ...
    def delete_chunks(self, chunk_ids: list[str]) -> None: ...
    def query_keyword(self, query: str, top_k: int) -> list[dict]: ...
    def clear(self) -> None: ...


@dataclass
class QdrantVectorStore(DenseStore):
    config: Settings

    @cached_property
    def _client(self):
        _require_dependency("qdrant-client", QdrantClient)
        kwargs = {"url": self.config.QDRANT_URL}
        if self.config.QDRANT_API_KEY:
            kwargs["api_key"] = self.config.QDRANT_API_KEY
        return QdrantClient(**kwargs)

    def _ensure_collection(self, embedding_dimension: int) -> None:
        """若 Qdrant collection 不存在则创建，已存在则跳过（幂等操作）。"""
        client = self._client
        exists = bool(client.collection_exists(self.config.QDRANT_COLLECTION))
        if exists:
            return
        client.create_collection(
            collection_name=self.config.QDRANT_COLLECTION,
            vectors_config=qdrant_models.VectorParams(
                size=embedding_dimension,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[ChunkMeta], vectors: list[list[float]]) -> None:
        if not chunks:
            return

        client = self._client
        self._ensure_collection(chunks[0].embedding_dimension)
        points = [
            qdrant_models.PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "chunk_index": chunk.chunk_index,
                    "nearest_heading": chunk.nearest_heading,
                    "source_rel_path": chunk.source_rel_path,
                    "title": chunk.title,
                    "content_hash": chunk.content_hash,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimension": chunk.embedding_dimension,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]
        client.upsert(
            collection_name=self.config.QDRANT_COLLECTION,
            points=points,
            wait=True,
        )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        client = self._client
        client.delete(
            collection_name=self.config.QDRANT_COLLECTION,
            points_selector=qdrant_models.PointIdsList(points=chunk_ids),
            wait=True,
        )

    def query_dense(self, query_vector: list[float], top_k: int) -> list[dict]:
        client = self._client
        results = client.search(
            collection_name=self.config.QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        candidates: list[dict] = []
        for point in results:
            payload = dict(point.payload or {})
            candidates.append(
                {
                    "chunk_id": str(point.id),
                    "score": float(point.score),
                    "metadata": payload,
                    "document": payload.get("text", ""),
                    "source": "dense",
                }
            )
        return candidates

    def clear(self) -> None:
        client = self._client
        if client.collection_exists(self.config.QDRANT_COLLECTION):
            client.delete_collection(self.config.QDRANT_COLLECTION)


@dataclass
class ElasticsearchKeywordStore(KeywordStore):
    config: Settings

    @cached_property
    def _client(self):
        _require_dependency("elasticsearch", Elasticsearch)
        kwargs: dict = {"hosts": [self.config.ELASTICSEARCH_URL]}
        if self.config.ELASTICSEARCH_API_KEY:
            kwargs["api_key"] = self.config.ELASTICSEARCH_API_KEY
        elif self.config.ELASTICSEARCH_USERNAME or self.config.ELASTICSEARCH_PASSWORD:
            kwargs["basic_auth"] = (
                self.config.ELASTICSEARCH_USERNAME,
                self.config.ELASTICSEARCH_PASSWORD,
            )
        if self.config.ELASTICSEARCH_CA_CERT_PATH:
            kwargs["ca_certs"] = self.config.ELASTICSEARCH_CA_CERT_PATH
        return Elasticsearch(**kwargs)

    def _ensure_index(self) -> None:
        """若 ES index 不存在则创建并设置 mapping，已存在则跳过（幂等操作）。"""
        client = self._client
        if client.indices.exists(index=self.config.ELASTICSEARCH_INDEX):
            return
        client.indices.create(
            index=self.config.ELASTICSEARCH_INDEX,
            mappings={
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "article_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "title": {"type": "text", "analyzer": self.config.ELASTICSEARCH_ANALYZER},
                    "nearest_heading": {
                        "type": "text",
                        "analyzer": self.config.ELASTICSEARCH_ANALYZER,
                    },
                    "source_rel_path": {"type": "keyword"},
                    "content_hash": {"type": "keyword"},
                    "embedding_model": {"type": "keyword"},
                    "embedding_dimension": {"type": "integer"},
                    "text": {"type": "text", "analyzer": self.config.ELASTICSEARCH_ANALYZER},
                }
            },
        )

    def upsert_chunks(self, chunks: list[ChunkMeta]) -> None:
        if not chunks:
            return

        client = self._client
        self._ensure_index()
        actions = [
            {
                "_op_type": "index",
                "_index": self.config.ELASTICSEARCH_INDEX,
                "_id": chunk.chunk_id,
                "_source": {
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "chunk_index": chunk.chunk_index,
                    "nearest_heading": chunk.nearest_heading,
                    "source_rel_path": chunk.source_rel_path,
                    "title": chunk.title,
                    "content_hash": chunk.content_hash,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimension": chunk.embedding_dimension,
                    "text": chunk.text,
                },
            }
            for chunk in chunks
        ]
        helpers.bulk(client, actions)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        client = self._client
        client.delete_by_query(
            index=self.config.ELASTICSEARCH_INDEX,
            query={"terms": {"chunk_id": chunk_ids}},
            refresh=True,
        )

    def query_keyword(self, query: str, top_k: int) -> list[dict]:
        client = self._client
        response = client.search(
            index=self.config.ELASTICSEARCH_INDEX,
            size=top_k,
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "nearest_heading^2", "text"],
                }
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        candidates: list[dict] = []
        for hit in hits:
            source = dict(hit.get("_source", {}))
            candidates.append(
                {
                    "chunk_id": source.get("chunk_id", hit.get("_id", "")),
                    "score": float(hit.get("_score") or 0.0),
                    "metadata": source,
                    "document": source.get("text", ""),
                    "source": "keyword",
                }
            )
        return candidates

    def clear(self) -> None:
        client = self._client
        if client.indices.exists(index=self.config.ELASTICSEARCH_INDEX):
            client.indices.delete(index=self.config.ELASTICSEARCH_INDEX)


def get_dense_store(config: Settings) -> DenseStore:
    return QdrantVectorStore(config)


def get_keyword_store(config: Settings) -> KeywordStore:
    return ElasticsearchKeywordStore(config)


def upsert_dense_chunks(
    chunks: list[ChunkMeta],
    vectors: list[list[float]],
    config: Settings,
) -> None:
    get_dense_store(config).upsert_chunks(chunks, vectors)


def upsert_keyword_chunks(chunks: list[ChunkMeta], config: Settings) -> None:
    get_keyword_store(config).upsert_chunks(chunks)


def delete_dense_chunks(chunk_ids: list[str], config: Settings) -> None:
    get_dense_store(config).delete_chunks(chunk_ids)


def delete_keyword_chunks(chunk_ids: list[str], config: Settings) -> None:
    get_keyword_store(config).delete_chunks(chunk_ids)


def query_dense(query_vector: list[float], top_k: int, config: Settings) -> list[dict]:
    return get_dense_store(config).query_dense(query_vector, top_k)


def query_keyword(query: str, top_k: int, config: Settings) -> list[dict]:
    return get_keyword_store(config).query_keyword(query, top_k)


def clear_dense_store(config: Settings) -> None:
    get_dense_store(config).clear()


def clear_keyword_store(config: Settings) -> None:
    get_keyword_store(config).clear()


def check_consistency(
    config: Settings,
    manifest: IndexManifest,
    embedding_dimension: int | None = None,
) -> None:
    """校验当前配置与 manifest 记录是否一致，不一致则抛出 RuntimeError 并提示重建索引。

    检查项：embedding_model、embedding_dimension、vector_store、keyword_store、
    retrieval_mode、vector_distance_metric、qdrant_collection、elasticsearch_index、chunker_config。
    """
    errors: list[str] = []

    if manifest.embedding_model != config.EMBEDDING_MODEL:
        errors.append(
            f"embedding_model mismatch: manifest={manifest.embedding_model}, "
            f"config={config.EMBEDDING_MODEL}"
        )

    if (
        embedding_dimension is not None
        and manifest.embedding_dimension
        and manifest.embedding_dimension != embedding_dimension
    ):
        errors.append(
            f"embedding_dimension mismatch: manifest={manifest.embedding_dimension}, "
            f"current={embedding_dimension}"
        )

    if manifest.vector_store != config.VECTOR_STORE:
        errors.append(
            f"vector_store mismatch: manifest={manifest.vector_store}, "
            f"config={config.VECTOR_STORE}"
        )

    if manifest.keyword_store != config.KEYWORD_STORE:
        errors.append(
            f"keyword_store mismatch: manifest={manifest.keyword_store}, "
            f"config={config.KEYWORD_STORE}"
        )

    if manifest.retrieval_mode != config.RETRIEVAL_MODE:
        errors.append(
            f"retrieval_mode mismatch: manifest={manifest.retrieval_mode}, "
            f"config={config.RETRIEVAL_MODE}"
        )

    if manifest.vector_distance_metric != config.VECTOR_DISTANCE_METRIC:
        errors.append(
            f"vector_distance_metric mismatch: manifest={manifest.vector_distance_metric}, "
            f"config={config.VECTOR_DISTANCE_METRIC}"
        )

    if manifest.qdrant_collection != config.QDRANT_COLLECTION:
        errors.append(
            f"qdrant_collection mismatch: manifest={manifest.qdrant_collection}, "
            f"config={config.QDRANT_COLLECTION}"
        )

    if manifest.elasticsearch_index != config.ELASTICSEARCH_INDEX:
        errors.append(
            f"elasticsearch_index mismatch: manifest={manifest.elasticsearch_index}, "
            f"config={config.ELASTICSEARCH_INDEX}"
        )

    stored_chunker = manifest.chunker_config or {}
    expected_chunker = {
        "chunk_target_min_chars": config.CHUNK_TARGET_MIN_CHARS,
        "chunk_target_max_chars": config.CHUNK_TARGET_MAX_CHARS,
        "chunk_overlap": config.CHUNK_OVERLAP,
    }
    if stored_chunker != expected_chunker:
        errors.append(
            f"chunker_config mismatch: manifest={stored_chunker}, "
            f"config={expected_chunker}"
        )

    if errors:
        msg = "\n".join(errors) + (
            "\n\nTo rebuild the index, run:\n  mooomoocatrag ingest --rebuild"
        )
        raise RuntimeError(msg)
