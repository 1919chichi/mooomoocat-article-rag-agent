from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest
from mooomoocatrag.rag.vector_store import (
    ElasticsearchKeywordStore,
    QdrantVectorStore,
    check_consistency,
    clear_dense_store,
    clear_keyword_store,
    delete_dense_chunks,
    delete_keyword_chunks,
    query_dense,
    query_keyword,
    upsert_dense_chunks,
    upsert_keyword_chunks,
)


@pytest.fixture
def settings():
    return Settings(
        VECTOR_STORE="qdrant",
        KEYWORD_STORE="elasticsearch",
        RETRIEVAL_MODE="hybrid_rrf",
        VECTOR_DISTANCE_METRIC="cosine",
        EMBEDDING_MODEL="test-model",
        QDRANT_URL="http://localhost:6333",
        QDRANT_COLLECTION="mooomoocat_articles_v1",
        ELASTICSEARCH_URL="https://localhost:9200",
        ELASTICSEARCH_USERNAME="elastic",
        ELASTICSEARCH_PASSWORD="secret",
        ELASTICSEARCH_INDEX="mooomoocat_article_chunks_v1",
        ELASTICSEARCH_ANALYZER="smartcn",
        CHUNK_TARGET_MIN_CHARS=600,
        CHUNK_TARGET_MAX_CHARS=1000,
        CHUNK_OVERLAP=100,
    )


def make_chunk(
    chunk_id: str = "chunk-1",
    article_id: str = "article-1",
    embedding_model: str = "test-model",
    embedding_dimension: int = 1536,
) -> ChunkMeta:
    return ChunkMeta(
        chunk_id=chunk_id,
        article_id=article_id,
        chunk_index=0,
        nearest_heading="Test Heading",
        text="This is test chunk text.",
        source_rel_path="articles/test.md",
        title="Test Article",
        content_hash="abc123",
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )


class TestQdrantVectorStore:
    @patch("mooomoocatrag.rag.vector_store.QdrantClient")
    def test_upsert_creates_collection_and_points(self, mock_client_class, settings):
        store = QdrantVectorStore(settings)
        mock_client = mock_client_class.return_value
        mock_client.collection_exists.return_value = False

        store.upsert_chunks([make_chunk()], [[0.1, 0.2, 0.3]])

        mock_client.create_collection.assert_called_once()
        mock_client.upsert.assert_called_once()
        call_kwargs = mock_client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == settings.QDRANT_COLLECTION
        assert call_kwargs["wait"] is True

    @patch("mooomoocatrag.rag.vector_store.QdrantClient")
    def test_query_dense_returns_normalized_candidates(self, mock_client_class, settings):
        store = QdrantVectorStore(settings)
        mock_client = mock_client_class.return_value
        point = MagicMock()
        point.id = "chunk-1"
        point.score = 0.91
        point.payload = {
            "article_id": "article-1",
            "chunk_index": 0,
            "nearest_heading": "Heading",
            "source_rel_path": "a.md",
            "title": "Title",
            "content_hash": "hash",
            "embedding_model": "test-model",
            "embedding_dimension": 1536,
            "text": "doc1",
        }
        mock_client.search.return_value = [point]

        results = store.query_dense([0.1, 0.2], top_k=5)

        mock_client.search.assert_called_once()
        assert results == [
            {
                "chunk_id": "chunk-1",
                "score": 0.91,
                "metadata": point.payload,
                "document": "doc1",
                "source": "dense",
            }
        ]

    @patch("mooomoocatrag.rag.vector_store.QdrantClient")
    def test_delete_and_clear(self, mock_client_class, settings):
        store = QdrantVectorStore(settings)
        mock_client = mock_client_class.return_value
        mock_client.collection_exists.return_value = True

        store.delete_chunks(["chunk-1", "chunk-2"])
        store.clear()

        mock_client.delete.assert_called_once()
        mock_client.delete_collection.assert_called_once_with(settings.QDRANT_COLLECTION)


class TestElasticsearchKeywordStore:
    @patch("mooomoocatrag.rag.vector_store.Elasticsearch")
    def test_upsert_creates_index_and_bulk_writes(self, mock_es_class, settings):
        store = ElasticsearchKeywordStore(settings)
        mock_client = mock_es_class.return_value
        mock_client.indices.exists.return_value = False

        with patch("mooomoocatrag.rag.vector_store.helpers.bulk") as mock_bulk:
            store.upsert_chunks([make_chunk()])

        mock_client.indices.create.assert_called_once()
        mock_bulk.assert_called_once()

    @patch("mooomoocatrag.rag.vector_store.Elasticsearch")
    def test_query_keyword_returns_normalized_candidates(self, mock_es_class, settings):
        store = ElasticsearchKeywordStore(settings)
        mock_client = mock_es_class.return_value
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_score": 12.3,
                        "_source": {
                            "chunk_id": "chunk-1",
                            "article_id": "article-1",
                            "chunk_index": 0,
                            "nearest_heading": "Heading",
                            "source_rel_path": "a.md",
                            "title": "Title",
                            "content_hash": "hash",
                            "embedding_model": "test-model",
                            "embedding_dimension": 1536,
                            "text": "doc1",
                        },
                    }
                ]
            }
        }

        results = store.query_keyword("cats", top_k=5)

        mock_client.search.assert_called_once()
        assert results == [
            {
                "chunk_id": "chunk-1",
                "score": 12.3,
                "metadata": {
                    "chunk_id": "chunk-1",
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "Heading",
                    "source_rel_path": "a.md",
                    "title": "Title",
                    "content_hash": "hash",
                    "embedding_model": "test-model",
                    "embedding_dimension": 1536,
                    "text": "doc1",
                },
                "document": "doc1",
                "source": "keyword",
            }
        ]

    @patch("mooomoocatrag.rag.vector_store.Elasticsearch")
    def test_delete_and_clear(self, mock_es_class, settings):
        store = ElasticsearchKeywordStore(settings)
        mock_client = mock_es_class.return_value
        mock_client.indices.exists.return_value = True

        store.delete_chunks(["chunk-1"])
        store.clear()

        mock_client.delete_by_query.assert_called_once()
        mock_client.indices.delete.assert_called_once_with(index=settings.ELASTICSEARCH_INDEX)


class TestModuleWrappers:
    @patch("mooomoocatrag.rag.vector_store.QdrantVectorStore")
    def test_dense_wrappers_delegate(self, mock_store_class, settings):
        store = mock_store_class.return_value

        upsert_dense_chunks([make_chunk()], [[0.1, 0.2]], settings)
        query_dense([0.1, 0.2], 4, settings)
        delete_dense_chunks(["chunk-1"], settings)
        clear_dense_store(settings)

        store.upsert_chunks.assert_called_once()
        store.query_dense.assert_called_once_with([0.1, 0.2], 4)
        store.delete_chunks.assert_called_once_with(["chunk-1"])
        store.clear.assert_called_once_with()

    @patch("mooomoocatrag.rag.vector_store.ElasticsearchKeywordStore")
    def test_keyword_wrappers_delegate(self, mock_store_class, settings):
        store = mock_store_class.return_value

        upsert_keyword_chunks([make_chunk()], settings)
        query_keyword("cats", 4, settings)
        delete_keyword_chunks(["chunk-1"], settings)
        clear_keyword_store(settings)

        store.upsert_chunks.assert_called_once()
        store.query_keyword.assert_called_once_with("cats", 4)
        store.delete_chunks.assert_called_once_with(["chunk-1"])
        store.clear.assert_called_once_with()


class TestCheckConsistency:
    def test_embedding_model_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="qdrant",
            keyword_store="elasticsearch",
            retrieval_mode="hybrid_rrf",
            vector_distance_metric="cosine",
            embedding_model="different-model",
            embedding_dimension=1536,
            qdrant_collection="mooomoocat_articles_v1",
            elasticsearch_index="mooomoocat_article_chunks_v1",
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="embedding_model mismatch"):
            check_consistency(settings, manifest)

    def test_keyword_store_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="qdrant",
            keyword_store="other",
            retrieval_mode="hybrid_rrf",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            qdrant_collection="mooomoocat_articles_v1",
            elasticsearch_index="mooomoocat_article_chunks_v1",
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="keyword_store mismatch"):
            check_consistency(settings, manifest)

    def test_retrieval_mode_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="qdrant",
            keyword_store="elasticsearch",
            retrieval_mode="dense_only",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            qdrant_collection="mooomoocat_articles_v1",
            elasticsearch_index="mooomoocat_article_chunks_v1",
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="retrieval_mode mismatch"):
            check_consistency(settings, manifest)

    def test_collection_and_index_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="qdrant",
            keyword_store="elasticsearch",
            retrieval_mode="hybrid_rrf",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            qdrant_collection="other_collection",
            elasticsearch_index="other_index",
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="qdrant_collection mismatch"):
            check_consistency(settings, manifest)
