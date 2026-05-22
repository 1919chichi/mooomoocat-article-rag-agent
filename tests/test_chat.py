from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest, RetrievalResult
from mooomoocatrag.rag.chat import chat_turn, NO_INSUFFICIENT_CONTENTResponse
from mooomoocatrag.rag.intent.types import IntentResult, IntentType


@pytest.fixture
def settings():
    return Settings(
        TOP_K=8,
        SIMILARITY_THRESHOLD=0.5,
        RAG_CONTEXT_TOKEN_BUDGET=6000,
        LLM_CONTEXT_WINDOW=32768,
        MAX_OUTPUT_TOKENS=2048,
        CHAT_HISTORY_TURNS=4,
        LLM_MODEL="test-llm-model",
        LLM_BASE_URL="https://api.test.com",
        LLM_API_KEY="test-api-key",
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
        },
    )


@pytest.fixture
def sample_chunk():
    return ChunkMeta(
        chunk_id="article-1_0",
        article_id="article-1",
        chunk_index=0,
        nearest_heading="Introduction",
        text="This is a test article about cats.",
        source_rel_path="articles/cats.md",
        title="All About Cats",
        content_hash="hash123",
        embedding_model="test-model",
        embedding_dimension=1536,
    )


@pytest.fixture
def sample_results(sample_chunk):
    chunk2 = ChunkMeta(
        chunk_id="article-1_1",
        article_id="article-1",
        chunk_index=1,
        nearest_heading="Cat Behavior",
        text="Cats love to nap in sunny spots and play with toys.",
        source_rel_path="articles/cats.md",
        title="All About Cats",
        content_hash="hash123",
        embedding_model="test-model",
        embedding_dimension=1536,
    )
    return [
        RetrievalResult(chunk=sample_chunk, similarity=0.95),
        RetrievalResult(chunk=chunk2, similarity=0.85),
    ]


class TestChatTurn:
    @pytest.fixture(autouse=True)
    def mock_intent_router(self):
        """Force QA intent so existing tests exercise the QA handler path."""
        qa_result = IntentResult(intent=IntentType.QA, confidence=0.9, method="rule")
        with patch("mooomoocatrag.rag.chat.IntentRouter") as mock_router_cls:
            mock_router_cls.return_value.classify.return_value = qa_result
            yield mock_router_cls

    @staticmethod
    def _llm_messages(mock_openai_class):
        mock_client = mock_openai_class.return_value
        return mock_client.chat.completions.create.call_args[1]["messages"]

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    def test_forces_retrieval_on_every_turn(self, mock_retrieve, settings, manifest, sample_results):
        """Test that retrieval is always called (enforced at code level)"""
        mock_retrieve.return_value = sample_results

        with patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
            mock_client.chat.completions.create.return_value = mock_response

            chat_turn("test query", [], settings, manifest)

            # Verify retrieve was called
            mock_retrieve.assert_called_once_with("test query", settings, manifest)

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    def test_no_retrieval_result_returns_no_content_message(
        self, mock_retrieve, settings, manifest
    ):
        """Test when no results retrieved, returns no sufficient content message"""
        mock_retrieve.return_value = []

        response = chat_turn("test query", [], settings, manifest)

        assert response.answer == NO_INSUFFICIENT_CONTENTResponse
        assert response.citations == []
        assert response.retrieved_count == 0

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_budget_normal_keeps_recent_valid_history(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test normal budget still includes recent valid history."""
        mock_retrieve.return_value = sample_results

        history = []
        for i in range(10):  # 5 user + 5 assistant = 10 messages > 4 * 2 = 8
            history.append({"role": "user", "content": f"User message {i}"})
            history.append({"role": "assistant", "content": f"Assistant message {i}"})
        history.extend(
            [
                {"role": "system", "content": "invalid history role"},
                {"role": "tool", "content": "invalid history role"},
            ]
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        chat_turn("test query", history, settings, manifest)

        messages = self._llm_messages(mock_openai_class)

        # Exclude system prompt and current user message containing retrieved context.
        history_msgs = messages[1:-1]
        assert history_msgs == [
            {"role": "user", "content": "User message 6"},
            {"role": "assistant", "content": "Assistant message 6"},
            {"role": "user", "content": "User message 7"},
            {"role": "assistant", "content": "Assistant message 7"},
            {"role": "user", "content": "User message 8"},
            {"role": "assistant", "content": "Assistant message 8"},
            {"role": "user", "content": "User message 9"},
            {"role": "assistant", "content": "Assistant message 9"},
        ]

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_budget_trim_keeps_highest_similarity_chunks(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_chunk
    ):
        """Test budget trimming drops low-similarity chunks before high-similarity chunks."""
        high = replace(
            sample_chunk,
            chunk_id="article-1_high",
            chunk_index=0,
            text="H" * 120,
        )
        medium = replace(
            sample_chunk,
            chunk_id="article-1_medium",
            chunk_index=1,
            text="M" * 120,
        )
        low = replace(
            sample_chunk,
            chunk_id="article-1_low",
            chunk_index=2,
            text="L" * 120,
        )
        mock_retrieve.return_value = [
            RetrievalResult(chunk=low, similarity=0.51),
            RetrievalResult(chunk=high, similarity=0.99),
            RetrievalResult(chunk=medium, similarity=0.75),
        ]
        settings.LLM_CONTEXT_WINDOW = 360
        settings.MAX_OUTPUT_TOKENS = 100

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        response = chat_turn("test query", [], settings, manifest)

        messages = self._llm_messages(mock_openai_class)
        current_user_content = messages[-1]["content"]
        assert "H" * 120 in current_user_content
        assert "M" * 120 in current_user_content
        assert "L" * 120 not in current_user_content
        assert response.retrieved_count == 2

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_budget_constraint_trims_chunks_first(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test when budget is insufficient, chunks are reduced before history"""
        # Set very low budget
        settings.LLM_CONTEXT_WINDOW = 500
        settings.MAX_OUTPUT_TOKENS = 100
        settings.RAG_CONTEXT_TOKEN_BUDGET = 10000  # Large to ensure chunks are issue

        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        # Provide some history
        history = [
            {"role": "user", "content": "Tell me about cats"},
            {"role": "assistant", "content": "Cats are great!"},
        ]

        chat_turn("test query", history, settings, manifest)

        # Verify LLM was called
        mock_client.chat.completions.create.assert_called_once()

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_returns_correct_retrieved_count(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test returned retrieved_count matches actual results used"""
        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        response = chat_turn("test query", [], settings, manifest)

        # retrieved_count should be same as sample_results length (or less if budget trimmed)
        assert response.retrieved_count <= len(sample_results)

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_citations_are_generated(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test citations are returned from chat_turn"""
        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        response = chat_turn("test query", [], settings, manifest)

        assert len(response.citations) > 0
        # Citations should use relative paths
        for citation in response.citations:
            assert "/Users/" not in citation
            assert "/home/" not in citation

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_llm_called_with_correct_params(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test LLM is called with correct base_url, api_key, model"""
        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        chat_turn("test query", [], settings, manifest)

        mock_openai_class.assert_called_once_with(
            base_url=settings.effective_llm_base_url,
            api_key=settings.effective_llm_api_key,
        )
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == settings.LLM_MODEL
        assert call_kwargs["max_tokens"] == settings.MAX_OUTPUT_TOKENS

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_empty_answer_handling(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test handling of empty LLM response"""
        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        mock_client.chat.completions.create.return_value = mock_response

        response = chat_turn("test query", [], settings, manifest)

        # Should handle None content gracefully
        assert response.answer == ""

    @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
    @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
    def test_history_not_included_when_empty(
        self, mock_openai_class, mock_retrieve, settings, manifest, sample_results
    ):
        """Test that empty history doesn't add extra messages"""
        mock_retrieve.return_value = sample_results

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        mock_client.chat.completions.create.return_value = mock_response

        chat_turn("test query", [], settings, manifest)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]

        # Should only have system + user (no history)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
