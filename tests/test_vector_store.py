from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import chromadb
import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest
from mooomoocatrag.rag.vector_store import (
    COLLECTION_NAME,
    add_chunks,
    check_consistency,
    delete_chunks,
    get_or_create_collection,
    query_similar,
)


@pytest.fixture
def ephemeral_client():
    return chromadb.EphemeralClient()


@pytest.fixture
def settings():
    return Settings(
        VECTOR_STORE="chroma",
        VECTOR_DISTANCE_METRIC="cosine",
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


class TestGetOrCreateCollection:
    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_creates_with_metadata(self, mock_persistent_client):
        settings = Settings(
            VECTOR_STORE="chroma",
            VECTOR_DISTANCE_METRIC="cosine",
        )

        mock_client = mock_persistent_client.return_value
        mock_collection = mock_client.get_or_create.return_value

        collection = get_or_create_collection(settings, "my-model", 1536)

        mock_client.get_or_create.assert_called_once_with(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "schema_version": "1",
                "embedding_model": "my-model",
                "embedding_dimension": "1536",
            },
        )
        assert collection == mock_collection


class TestAddChunks:
    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_adds_chunks_with_metadata(self, mock_persistent_client):
        settings = Settings(VECTOR_DISTANCE_METRIC="cosine")

        mock_client = mock_persistent_client.return_value
        mock_collection = mock_client.get_or_create.return_value

        chunks = [make_chunk("chunk-1"), make_chunk("chunk-2")]
        vectors = [[0.1, 0.2], [0.3, 0.4]]

        add_chunks(chunks, vectors, settings)

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args.kwargs
        assert call_kwargs["ids"] == ["chunk-1", "chunk-2"]
        assert call_kwargs["documents"] == [
            "This is test chunk text.",
            "This is test chunk text.",
        ]
        assert call_kwargs["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]

        metadata = call_kwargs["metadatas"]
        assert metadata[0]["article_id"] == "article-1"
        assert metadata[0]["chunk_index"] == 0
        assert metadata[0]["nearest_heading"] == "Test Heading"
        assert metadata[0]["source_rel_path"] == "articles/test.md"
        assert metadata[0]["title"] == "Test Article"
        assert metadata[0]["content_hash"] == "abc123"
        assert metadata[0]["embedding_model"] == "test-model"
        assert metadata[0]["embedding_dimension"] == 1536

    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_empty_chunks(self, mock_persistent_client):
        settings = Settings()
        add_chunks([], [], settings)
        mock_persistent_client.return_value.get_or_create.assert_not_called()


class TestDeleteChunks:
    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_deletes_by_ids(self, mock_persistent_client):
        settings = Settings()

        mock_client = mock_persistent_client.return_value
        mock_collection = mock_client.get_or_create.return_value

        delete_chunks(["chunk-1", "chunk-2"], settings)

        mock_collection.delete.assert_called_once_with(ids=["chunk-1", "chunk-2"])

    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_empty_delete(self, mock_persistent_client):
        settings = Settings()
        delete_chunks([], settings)
        mock_persistent_client.return_value.get_or_create.assert_not_called()


class TestQuerySimilar:
    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_overfetch(self, mock_persistent_client):
        settings = Settings()

        mock_client = mock_persistent_client.return_value
        mock_collection = mock_client.get_or_create.return_value
        mock_collection.query.return_value = {
            "distances": [[0.1, 0.2, 0.3, 0.4, 0.5]],
            "metadatas": [[{}, {}, {}, {}, {}]],
            "documents": [["d1", "d2", "d3", "d4", "d5"]],
        }

        result = query_similar([0.1, 0.2], top_k=2, config=settings)

        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2]],
            n_results=12,
            include=["distances", "metadatas", "documents"],
        )
        assert "distances" in result[0]
        assert "metadatas" in result[0]
        assert "documents" in result[0]

    @patch("mooomoocatrag.rag.vector_store.chromadb.PersistentClient")
    def test_overfetch_top_k_10(self, mock_persistent_client):
        settings = Settings()

        mock_client = mock_persistent_client.return_value
        mock_collection = mock_client.get_or_create.return_value
        mock_collection.query.return_value = {
            "distances": [[0.1] * 20],
            "metadatas": [[{}] * 20],
            "documents": [["d"] * 20],
        }

        result = query_similar([0.1, 0.2], top_k=10, config=settings)

        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2]],
            n_results=30,
            include=["distances", "metadatas", "documents"],
        )
        assert len(result[0]["distances"]) == 20


class TestCheckConsistency:
    def test_embedding_model_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="chroma",
            vector_distance_metric="cosine",
            embedding_model="different-model",
            embedding_dimension=1536,
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="embedding_model mismatch"):
            check_consistency(settings, manifest)

    def test_vector_store_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="other",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="vector_store mismatch"):
            check_consistency(settings, manifest)

    def test_vector_distance_metric_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="chroma",
            vector_distance_metric="euclidean",
            embedding_model="test-model",
            embedding_dimension=1536,
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="vector_distance_metric mismatch"):
            check_consistency(settings, manifest)

    def test_embedding_dimension_mismatch(self):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            VECTOR_STORE="chroma",
            VECTOR_DISTANCE_METRIC="cosine",
            CHUNK_TARGET_MIN_CHARS=600,
            CHUNK_TARGET_MAX_CHARS=1000,
            CHUNK_OVERLAP=100,
        )
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="chroma",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=768,
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        with pytest.raises(RuntimeError, match="embedding_dimension mismatch"):
            check_consistency(settings, manifest, embedding_dimension=1536)

    def test_chunker_config_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="chroma",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            chunker_config={
                "chunk_target_min_chars": 500,
                "chunk_target_max_chars": 900,
                "chunk_overlap": 50,
            },
        )

        with pytest.raises(RuntimeError, match="chunker_config mismatch"):
            check_consistency(settings, manifest)

    def test_all_mismatch(self, settings):
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="other",
            vector_distance_metric="euclidean",
            embedding_model="different",
            embedding_dimension=768,
            chunker_config={
                "chunk_target_min_chars": 500,
                "chunk_target_max_chars": 900,
                "chunk_overlap": 50,
            },
        )

        with pytest.raises(RuntimeError) as exc_info:
            check_consistency(settings, manifest)

        error_msg = str(exc_info.value)
        assert "embedding_model mismatch" in error_msg
        assert "vector_store mismatch" in error_msg
        assert "vector_distance_metric mismatch" in error_msg
        assert "chunker_config mismatch" in error_msg
        assert "mooomoocatrag ingest --rebuild" in error_msg

    def test_consistent(self):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            VECTOR_STORE="chroma",
            VECTOR_DISTANCE_METRIC="cosine",
            CHUNK_TARGET_MIN_CHARS=600,
            CHUNK_TARGET_MAX_CHARS=1000,
            CHUNK_OVERLAP=100,
        )
        manifest = IndexManifest(
            schema_version=1,
            source_root="",
            vector_store="chroma",
            vector_distance_metric="cosine",
            embedding_model="test-model",
            embedding_dimension=1536,
            chunker_config={
                "chunk_target_min_chars": 600,
                "chunk_target_max_chars": 1000,
                "chunk_overlap": 100,
            },
        )

        check_consistency(settings, manifest)
