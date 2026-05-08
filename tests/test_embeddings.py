from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.rag.embeddings import _batch, embed_texts, _is_retryable


class MockEmbeddingItem:
    def __init__(self, embedding: list[float]):
        self.embedding = embedding


class MockEmbeddingResponse:
    def __init__(self, embeddings: list[list[float]]):
        self.data = [MockEmbeddingItem(e) for e in embeddings]


class TestBatching:
    def test_batch_evenly_divisible(self):
        items = list(range(10))
        batches = list(_batch(items, 3))
        assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    def test_batch_exact_multiple(self):
        items = list(range(9))
        batches = list(_batch(items, 3))
        assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]

    def test_batch_single_batch(self):
        items = list(range(5))
        batches = list(_batch(items, 10))
        assert batches == [[0, 1, 2, 3, 4]]

    def test_batch_empty(self):
        batches = list(_batch([], 3))
        assert batches == []


class TestEmbedTexts:
    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    def test_batching(self, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = [
            MockEmbeddingResponse([[0.1, 0.2], [0.3, 0.4]]),
            MockEmbeddingResponse([[0.5, 0.6]]),
        ]

        texts = ["a", "b", "c"]
        result = embed_texts(texts, settings)

        assert len(result) == 3
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]
        assert result[2] == [0.5, 0.6]
        assert mock_client.embeddings.create.call_count == 2

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    @patch("mooomoocatrag.rag.embeddings.time.sleep")
    def test_rate_limiting(self, mock_sleep, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = [
            MockEmbeddingResponse([[0.1, 0.2], [0.3, 0.4]]),
            MockEmbeddingResponse([[0.5, 0.6]]),
        ]

        texts = ["a", "b", "c"]
        embed_texts(texts, settings)

        assert mock_sleep.call_count == 1

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    @patch("mooomoocatrag.rag.embeddings.time.sleep")
    def test_retry_on_429(self, mock_sleep, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        error = Exception("Rate limit error 429")
        mock_client.embeddings.create.side_effect = [
            error,
            error,
            MockEmbeddingResponse([[0.1, 0.2], [0.3, 0.4]]),
        ]

        texts = ["a", "b"]
        result = embed_texts(texts, settings)

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        assert mock_sleep.call_count == 2

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    @patch("mooomoocatrag.rag.embeddings.time.sleep")
    def test_retry_on_500(self, mock_sleep, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        error = Exception("Internal server error 500")
        mock_client.embeddings.create.side_effect = [
            error,
            MockEmbeddingResponse([[0.1, 0.2], [0.3, 0.4]]),
        ]

        texts = ["a", "b"]
        result = embed_texts(texts, settings)

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        assert mock_sleep.call_count == 1

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    def test_no_retry_on_other_error(self, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("Some other error")

        texts = ["a", "b"]
        with pytest.raises(Exception, match="Some other error"):
            embed_texts(texts, settings)

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    def test_empty_texts(self, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=32,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        result = embed_texts([], settings)
        assert result == []
        mock_openai_class.return_value.embeddings.create.assert_not_called()

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    def test_order_preserved(self, mock_openai_class):
        settings = Settings(
            EMBEDDING_MODEL="test-model",
            EMBEDDING_BATCH_SIZE=2,
            EMBEDDING_REQUESTS_PER_MINUTE=60,
        )

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = [
            MockEmbeddingResponse([[0.2, 0.2], [0.1, 0.1]]),
            MockEmbeddingResponse([[0.3, 0.3]]),
        ]

        texts = ["second", "first", "third"]
        result = embed_texts(texts, settings)

        assert result[0] == [0.2, 0.2]
        assert result[1] == [0.1, 0.1]
        assert result[2] == [0.3, 0.3]


class TestIsRetryable:
    def test_retryable_429(self):
        assert _is_retryable(Exception("error 429")) is True

    def test_retryable_500(self):
        assert _is_retryable(Exception("error 500")) is True

    def test_retryable_502(self):
        assert _is_retryable(Exception("error 502")) is True

    def test_retryable_503(self):
        assert _is_retryable(Exception("error 503")) is True

    def test_retryable_504(self):
        assert _is_retryable(Exception("error 504")) is True

    def test_not_retryable(self):
        assert _is_retryable(Exception("connection error")) is False
