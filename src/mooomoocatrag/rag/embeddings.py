from __future__ import annotations

import time
from typing import Iterator

from openai import OpenAI

from mooomoocatrag.config import Settings


def embed_texts(texts: list[str], config: Settings) -> list[list[float]]:
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
