from __future__ import annotations

from unittest.mock import MagicMock, patch
import math

import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest, RetrievalResult
from mooomoocatrag.rag.retriever import retrieve


@pytest.fixture
def settings():
    return Settings(
        TOP_K=8,
        SIMILARITY_THRESHOLD=0.5,
        RAG_CONTEXT_TOKEN_BUDGET=6000,
        LLM_CONTEXT_WINDOW=32768,
        MAX_OUTPUT_TOKENS=2048,
        CHAT_HISTORY_TURNS=4,
        EMBEDDING_MODEL="test-embedding-model",
    )


@pytest.fixture
def manifest():
    return IndexManifest(
        schema_version=1,
        source_root="tests/fixtures",
        vector_store="chroma",
        vector_distance_metric="cosine",
        embedding_provider="openai-compatible",
        embedding_model="test-embedding-model",
        embedding_dimension=1536,
        articles={
            "article-1": {
                "content_hash": "hash123",
                "title": "Test Article 1",
            },
            "article-2": {
                "content_hash": "hash456",
                "title": "Test Article 2",
            },
        },
    )


@pytest.fixture
def mock_chunk():
    return ChunkMeta(
        chunk_id="article-1_0",
        article_id="article-1",
        chunk_index=0,
        nearest_heading="Introduction",
        text="This is test content for chunk 1",
        source_rel_path="test/article1.md",
        title="Test Article 1",
        content_hash="hash123",
        embedding_model="test-embedding-model",
        embedding_dimension=1536,
    )


def make_mock_result(chunk_id, article_id, chunk_index, content_hash, text, similarity):
    """Helper to create mock RetrievalResult"""
    chunk = ChunkMeta(
        chunk_id=chunk_id,
        article_id=article_id,
        chunk_index=chunk_index,
        nearest_heading="Test Heading",
        text=text,
        source_rel_path="test/article.md",
        title="Test Article",
        content_hash=content_hash,
        embedding_model="test-embedding-model",
        embedding_dimension=1536,
    )
    return RetrievalResult(chunk=chunk, similarity=similarity)


class TestRetrieve:
    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_retrieve_returns_empty_on_empty_query_vector(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test that empty embedding returns empty results"""
        mock_embed.return_value = []

        results = retrieve("test query", settings, manifest)

        assert results == []
        mock_query.assert_not_called()

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_retrieve_results_sorted_by_similarity(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test results are sorted by similarity descending"""
        mock_embed.return_value = [[0.1] * 1536]

        # Mock query_similar returning chunks with varying distances
        # distance 0.1 -> similarity 0.9, distance 0.3 -> similarity 0.7, distance 0.5 -> similarity 0.5
        # All above default threshold 0.5
        mock_query.return_value = [
            {
                "distances": [0.1, 0.3, 0.5],  # similarity: 0.9, 0.7, 0.5
                "metadatas": [
                    {"article_id": "article-1", "chunk_index": 0, "nearest_heading": "H1",
                     "source_rel_path": "a.md", "title": "A", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 1, "nearest_heading": "H2",
                     "source_rel_path": "b.md", "title": "B", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 2, "nearest_heading": "H3",
                     "source_rel_path": "c.md", "title": "C", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                ],
                "documents": ["doc1", "doc2", "doc3"],
            }
        ]

        results = retrieve("test query", settings, manifest)

        assert len(results) == 3
        # Should be sorted by similarity descending (0.9, 0.7, 0.5)
        assert results[0].similarity == 0.9
        assert results[1].similarity == 0.7
        assert results[2].similarity == 0.5
        mock_query.assert_called_once_with([0.1] * 1536, settings.TOP_K, settings)

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_similarity_threshold_filtering(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test SIMILARITY_THRESHOLD filters out low similarity results"""
        settings.SIMILARITY_THRESHOLD = 0.6
        mock_embed.return_value = [[0.1] * 1536]

        # distance 0.1 -> similarity 0.9, distance 0.3 -> similarity 0.7, distance 0.5 -> similarity 0.5
        mock_query.return_value = [
            {
                "distances": [0.1, 0.3, 0.5],  # similarity: 0.9, 0.7, 0.5
                "metadatas": [
                    {"article_id": "article-1", "chunk_index": 0, "nearest_heading": "H1",
                     "source_rel_path": "a.md", "title": "A", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 1, "nearest_heading": "H2",
                     "source_rel_path": "b.md", "title": "B", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 2, "nearest_heading": "H3",
                     "source_rel_path": "c.md", "title": "C", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                ],
                "documents": ["doc1", "doc2", "doc3"],
            }
        ]

        results = retrieve("test query", settings, manifest)

        # Only 0.9 and 0.7 pass threshold 0.6 (0.5 does not)
        assert len(results) == 2
        assert results[0].similarity == 0.9
        assert results[1].similarity == 0.7

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_manifest_filters_invalid_chunks(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test manifest filters chunks where article doesn't exist or content_hash mismatch"""
        mock_embed.return_value = [[0.1] * 1536]

        mock_query.return_value = [
            {
                "distances": [0.1, 0.1, 0.1],
                "metadatas": [
                    # Valid: article exists and hash matches
                    {"article_id": "article-1", "chunk_index": 0, "nearest_heading": "H1",
                     "source_rel_path": "a.md", "title": "A", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    # Invalid: article doesn't exist
                    {"article_id": "article-nonexistent", "chunk_index": 0, "nearest_heading": "H2",
                     "source_rel_path": "b.md", "title": "B", "content_hash": "hash999",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    # Invalid: hash doesn't match
                    {"article_id": "article-1", "chunk_index": 1, "nearest_heading": "H3",
                     "source_rel_path": "c.md", "title": "C", "content_hash": "wrong_hash",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                ],
                "documents": ["doc1", "doc2", "doc3"],
            }
        ]

        results = retrieve("test query", settings, manifest)

        # Only 1 valid result
        assert len(results) == 1
        assert results[0].chunk.article_id == "article-1"
        assert results[0].chunk.chunk_index == 0

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_token_budget_truncation(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test RAG_CONTEXT_TOKEN_BUDGET truncates results"""
        settings.RAG_CONTEXT_TOKEN_BUDGET = 100  # Very small budget
        mock_embed.return_value = [[0.1] * 1536]

        # Create chunks with known sizes
        long_text = "x" * 200  # ~134 tokens

        mock_query.return_value = [
            {
                "distances": [0.1, 0.1, 0.1],
                "metadatas": [
                    {"article_id": "article-1", "chunk_index": 0, "nearest_heading": "H1",
                     "source_rel_path": "a.md", "title": "A", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 1, "nearest_heading": "H2",
                     "source_rel_path": "b.md", "title": "B", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                    {"article_id": "article-1", "chunk_index": 2, "nearest_heading": "H3",
                     "source_rel_path": "c.md", "title": "C", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"},
                ],
                "documents": [long_text, long_text, long_text],
            }
        ]

        results = retrieve("test query", settings, manifest)

        # With budget 100 and each chunk ~134 tokens, only 1 chunk fits
        assert len(results) <= 1

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_top_k_truncation(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test TOP_K truncates final results"""
        settings.TOP_K = 2
        settings.RAG_CONTEXT_TOKEN_BUDGET = 10000  # Large budget
        mock_embed.return_value = [[0.1] * 1536]

        mock_query.return_value = [
            {
                "distances": [0.1] * 10,
                "metadatas": [
                    {"article_id": "article-1", "chunk_index": i, "nearest_heading": f"H{i}",
                     "source_rel_path": f"a{i}.md", "title": f"A{i}", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"}
                    for i in range(10)
                ],
                "documents": [f"doc{i}" for i in range(10)],
            }
        ]

        results = retrieve("test query", settings, manifest)

        assert len(results) == 2

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_empty_results(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test empty results from vector store returns empty list"""
        mock_embed.return_value = [[0.1] * 1536]
        mock_query.return_value = []

        results = retrieve("test query", settings, manifest)

        assert results == []

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_no_distances_in_results(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test handling when no distances returned"""
        mock_embed.return_value = [[0.1] * 1536]
        mock_query.return_value = [{"distances": [], "metadatas": [], "documents": []}]

        results = retrieve("test query", settings, manifest)

        assert results == []

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_similar")
    def test_cosine_distance_to_similarity_conversion(
        self, mock_query, mock_embed, settings, manifest
    ):
        """Test cosine distance 0-2 range is converted to similarity 0-1"""
        mock_embed.return_value = [[0.1] * 1536]

        mock_query.return_value = [
            {
                "distances": [0.0, 1.0, 2.0],  # similarity: 1.0, 0.0, 0.0 (clamped)
                "metadatas": [
                    {"article_id": "article-1", "chunk_index": i, "nearest_heading": "H",
                     "source_rel_path": "a.md", "title": "A", "content_hash": "hash123",
                     "embedding_model": "test", "embedding_dimension": "1536"}
                    for i in range(3)
                ],
                "documents": ["doc1", "doc2", "doc3"],
            }
        ]

        results = retrieve("test query", settings, manifest)

        # Distances 0.0 -> similarity 1.0, 1.0 -> 0.0, 2.0 -> 0.0 (clamped)
        assert results[0].similarity == 1.0
        # The other two should be filtered by threshold or at end
        assert all(r.similarity >= 0.5 for r in results)
