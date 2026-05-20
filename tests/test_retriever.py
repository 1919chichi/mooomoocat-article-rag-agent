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
        HYBRID_DENSE_TOP_K=8,
        HYBRID_KEYWORD_TOP_K=8,
        HYBRID_FINAL_TOP_K=8,
        HYBRID_RRF_K=60,
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
        vector_store="qdrant",
        keyword_store="elasticsearch",
        retrieval_mode="hybrid_rrf",
        vector_distance_metric="cosine",
        embedding_provider="openai-compatible",
        embedding_model="test-embedding-model",
        embedding_dimension=1536,
        qdrant_collection="mooomoocat_articles_v1",
        elasticsearch_index="mooomoocat_article_chunks_v1",
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
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_retrieve_returns_empty_on_empty_query_vector(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test that empty embedding returns empty results"""
        mock_embed.return_value = []

        results = retrieve("test query", settings, manifest)

        assert results == []
        mock_dense.assert_not_called()
        mock_keyword.assert_not_called()

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_retrieve_results_sorted_by_similarity(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test hybrid results are sorted by fused similarity descending"""
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = [
            {
                "chunk_id": "chunk-1",
                "score": 0.91,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "H1",
                    "source_rel_path": "a.md",
                    "title": "A",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc1",
                "source": "dense",
            },
            {
                "chunk_id": "chunk-2",
                "score": 0.70,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 1,
                    "nearest_heading": "H2",
                    "source_rel_path": "b.md",
                    "title": "B",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc2",
                "source": "dense",
            },
        ]
        mock_keyword.return_value = [
            {
                "chunk_id": "chunk-2",
                "score": 12.3,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 1,
                    "nearest_heading": "H2",
                    "source_rel_path": "b.md",
                    "title": "B",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc2",
                "source": "keyword",
            }
        ]

        results = retrieve("test query", settings, manifest)

        assert len(results) == 2
        assert results[0].chunk.chunk_id == "chunk-2"
        assert results[1].chunk.chunk_id == "chunk-1"
        assert set(results[0].sources) == {"dense", "keyword"}
        assert results[1].sources == ["dense"]
        mock_dense.assert_called_once_with(
            [0.1] * 1536,
            settings.HYBRID_DENSE_TOP_K,
            settings,
        )
        mock_keyword.assert_called_once_with(
            "test query",
            settings.HYBRID_KEYWORD_TOP_K,
            settings,
        )

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_similarity_threshold_filtering(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test fused similarity threshold filters out low-scoring results"""
        settings.SIMILARITY_THRESHOLD = 0.495
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = [
            {
                "chunk_id": "chunk-1",
                "score": 0.9,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "H1",
                    "source_rel_path": "a.md",
                    "title": "A",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc1",
                "source": "dense",
            },
            {
                "chunk_id": "chunk-2",
                "score": 0.7,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 1,
                    "nearest_heading": "H2",
                    "source_rel_path": "b.md",
                    "title": "B",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc2",
                "source": "dense",
            }
        ]
        mock_keyword.return_value = []

        results = retrieve("test query", settings, manifest)

        assert len(results) == 1
        assert results[0].chunk.chunk_id == "chunk-1"
        assert all(r.similarity >= 0.495 for r in results)

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_manifest_filters_invalid_chunks(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test manifest filters chunks where article doesn't exist or content_hash mismatch"""
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = [
            {
                "chunk_id": "valid",
                "score": 0.9,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "H1",
                    "source_rel_path": "a.md",
                    "title": "A",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc1",
                "source": "dense",
            },
            {
                "chunk_id": "invalid-article",
                "score": 0.9,
                "metadata": {
                    "article_id": "article-nonexistent",
                    "chunk_index": 0,
                    "nearest_heading": "H2",
                    "source_rel_path": "b.md",
                    "title": "B",
                    "content_hash": "hash999",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc2",
                "source": "dense",
            },
            {
                "chunk_id": "invalid-hash",
                "score": 0.9,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 1,
                    "nearest_heading": "H3",
                    "source_rel_path": "c.md",
                    "title": "C",
                    "content_hash": "wrong_hash",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "doc3",
                "source": "dense",
            }
        ]
        mock_keyword.return_value = []

        results = retrieve("test query", settings, manifest)

        # Only 1 valid result
        assert len(results) == 1
        assert results[0].chunk.article_id == "article-1"
        assert results[0].chunk.chunk_index == 0

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_token_budget_truncation(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test RAG_CONTEXT_TOKEN_BUDGET truncates results"""
        settings.RAG_CONTEXT_TOKEN_BUDGET = 100  # Very small budget
        mock_embed.return_value = [[0.1] * 1536]

        # Create chunks with known sizes
        long_text = "x" * 200  # ~134 tokens

        mock_dense.return_value = [
            {
                "chunk_id": f"chunk-{i}",
                "score": 0.9 - (i * 0.1),
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": i,
                    "nearest_heading": f"H{i}",
                    "source_rel_path": f"a{i}.md",
                    "title": f"A{i}",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": long_text,
                "source": "dense",
            }
            for i in range(3)
        ]
        mock_keyword.return_value = []

        results = retrieve("test query", settings, manifest)

        # With budget 100 and each chunk ~134 tokens, only 1 chunk fits
        assert len(results) <= 1

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_top_k_truncation(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test TOP_K truncates final results"""
        settings.HYBRID_FINAL_TOP_K = 2
        settings.SIMILARITY_THRESHOLD = 0.0
        settings.RAG_CONTEXT_TOKEN_BUDGET = 10000  # Large budget
        mock_embed.return_value = [[0.1] * 1536]

        mock_dense.return_value = [
            {
                "chunk_id": f"chunk-{i}",
                "score": 0.9 - (i * 0.01),
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": i,
                    "nearest_heading": f"H{i}",
                    "source_rel_path": f"a{i}.md",
                    "title": f"A{i}",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": "1536",
                },
                "document": f"doc{i}",
                "source": "dense",
            }
            for i in range(10)
        ]
        mock_keyword.return_value = []

        results = retrieve("test query", settings, manifest)

        assert len(results) == 2

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_empty_results(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        """Test empty results from both stores returns empty list"""
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = []
        mock_keyword.return_value = []

        results = retrieve("test query", settings, manifest)

        assert results == []

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_keyword_only_result_is_supported(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = []
        mock_keyword.return_value = [
            {
                "chunk_id": "keyword-only",
                "score": 12.0,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "H",
                    "source_rel_path": "a.md",
                    "title": "A",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "keyword doc",
                "source": "keyword",
            }
        ]

        results = retrieve("test query", settings, manifest)

        assert len(results) == 1
        assert results[0].sources == ["keyword"]

    @patch("mooomoocatrag.rag.retriever.embed_texts")
    @patch("mooomoocatrag.rag.retriever.query_keyword")
    @patch("mooomoocatrag.rag.retriever.query_dense")
    def test_keyword_query_failure_falls_back_to_dense(
        self, mock_dense, mock_keyword, mock_embed, settings, manifest
    ):
        mock_embed.return_value = [[0.1] * 1536]
        mock_dense.return_value = [
            {
                "chunk_id": "dense-only",
                "score": 0.9,
                "metadata": {
                    "article_id": "article-1",
                    "chunk_index": 0,
                    "nearest_heading": "H",
                    "source_rel_path": "a.md",
                    "title": "A",
                    "content_hash": "hash123",
                    "embedding_model": "test",
                    "embedding_dimension": 1536,
                },
                "document": "dense doc",
                "source": "dense",
            }
        ]
        mock_keyword.side_effect = RuntimeError("es down")

        results = retrieve("test query", settings, manifest)

        assert len(results) == 1
        assert results[0].sources == ["dense"]
