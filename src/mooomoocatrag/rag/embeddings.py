from __future__ import annotations

import abc
import time
import logging
from typing import Iterator

import httpx
from openai import OpenAI

from mooomoocatrag.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------

class EmbeddingStrategy(abc.ABC):
    """Abstract base for different embedding API backends."""

    @abc.abstractmethod
    def embed_texts(self, texts: list[str], config: Settings) -> list[list[float]]:
        ...


# ---------------------------------------------------------------------------
# OpenAI-compatible strategy (OpenAI, DashScope, Zhipu, etc.)
# ---------------------------------------------------------------------------

class OpenAIEmbeddingStrategy(EmbeddingStrategy):
    """Standard OpenAI /openai/embeddings endpoint."""

    def embed_texts(self, texts: list[str], config: Settings) -> list[list[float]]:
        if not texts:
            return []

        client = OpenAI(
            base_url=config.effective_embedding_base_url,
            api_key=config.effective_embedding_api_key,
        )

        all_embeddings: list[list[float]] = []
        batch_size = config.EMBEDDING_BATCH_SIZE
        rpm = config.EMBEDDING_REQUESTS_PER_MINUTE
        interval = 60.0 / rpm

        batches = list(_batch(texts, batch_size))
        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                time.sleep(interval)

            embedding = _embed_batch_with_retry(client, batch, config.EMBEDDING_MODEL)
            all_embeddings.extend(embedding)

        return all_embeddings


def _batch(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _embed_batch_with_retry(
    client: OpenAI, texts: list[str], model: str
) -> list[list[float]]:
    """带指数退避重试的批量 embedding 请求，对 429/5xx 最多重试 3 次。"""
    wait_time = 1.0
    for attempt in range(4):
        try:
            response = client.embeddings.create(
                model=model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if attempt == 3:
                raise
            if not _is_retryable(e):
                raise
            time.sleep(wait_time)
            wait_time *= 2


def _is_retryable(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "500" in msg or "502" in msg or "503" in msg or "504" in msg


# ---------------------------------------------------------------------------
# Volcengine ARK multimodal embedding strategy
# ---------------------------------------------------------------------------

class VolcengineEmbeddingStrategy(EmbeddingStrategy):
    """Volcengine ARK /embeddings/multimodal endpoint.

    Supports models like doubao-embedding-vision-251215 that use the
    multimodal endpoint with ``{"type":"text","text":"..."}`` input format.

    Note: The multimodal endpoint treats ``input`` as parts of a single
    document (text + image), returning one embedding per call.  We must
    send one request per text rather than batching.
    """

    def embed_texts(self, texts: list[str], config: Settings) -> list[list[float]]:
        if not texts:
            return []

        base_url = config.effective_embedding_base_url.rstrip("/")
        url = f"{base_url}/embeddings/multimodal"
        api_key = config.effective_embedding_api_key
        rpm = config.EMBEDDING_REQUESTS_PER_MINUTE
        interval = 60.0 / rpm

        all_embeddings: list[list[float]] = []
        for idx, text in enumerate(texts):
            if idx > 0:
                time.sleep(interval)
            embedding = self._embed_with_retry(url, api_key, text, config.EMBEDDING_MODEL)
            all_embeddings.append(embedding)

        return all_embeddings

    def _embed_with_retry(
        self, url: str, api_key: str, text: str, model: str
    ) -> list[float]:
        wait_time = 1.0
        for attempt in range(4):
            try:
                return self._call_api(url, api_key, text, model)
            except Exception as e:
                if attempt == 3:
                    raise
                if not _is_retryable(e):
                    raise
                time.sleep(wait_time)
                wait_time *= 2

    @staticmethod
    def _call_api(
        url: str, api_key: str, text: str, model: str
    ) -> list[float]:
        payload = {
            "model": model,
            "input": [{"type": "text", "text": text}],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        resp = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Volcengine embedding API error: status={resp.status_code} body={resp.text}"
            )

        data = resp.json()
        return data["data"]["embedding"]


# ---------------------------------------------------------------------------
# Strategy resolver
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = ("openai", "volcengine")


def get_embedding_strategy(config: Settings) -> EmbeddingStrategy:
    """根据 EMBEDDING_PROVIDER 配置返回对应的 embedding 策略实例。"""
    provider = config.EMBEDDING_PROVIDER.lower()
    if provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"Invalid EMBEDDING_PROVIDER={config.EMBEDDING_PROVIDER!r}, "
            f"must be one of {_VALID_PROVIDERS}"
        )

    if provider == "volcengine":
        logger.info("Using Volcengine embedding strategy")
        return VolcengineEmbeddingStrategy()

    return OpenAIEmbeddingStrategy()


# ---------------------------------------------------------------------------
# Public API (unchanged signature)
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], config: Settings) -> list[list[float]]:
    """调用 embedding 策略对文本列表批量向量化，返回顺序与输入一一对应。"""
    strategy = get_embedding_strategy(config)
    return strategy.embed_texts(texts, config)
