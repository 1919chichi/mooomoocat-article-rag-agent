from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mooomoocatrag.config import Settings


class FakeEmbeddingClient:
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]


@pytest.fixture
def fake_embedding_client():
    return FakeEmbeddingClient()


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_md_path(fixtures_dir):
    return fixtures_dir / "sample.md"


@pytest.fixture
def sample_txt_path(fixtures_dir):
    return fixtures_dir / "sample.txt"


@pytest.fixture
def fake_settings():
    return Settings(
        ARTICLE_SOURCE_DIR="tests/fixtures",
        DATA_DIR="data",
        EMBEDDING_MODEL="fake-embedding-model",
        EMBEDDING_MAX_TOKENS=8191,
        CHUNK_TARGET_MIN_CHARS=600,
        CHUNK_TARGET_MAX_CHARS=1000,
        CHUNK_OVERLAP=100,
    )
