from __future__ import annotations

import logging
import os

from pydantic_settings import BaseSettings

_settings_instance: Settings | None = None


def _mask_key(key: str) -> str:
    if len(key) <= 4:
        return "****"
    return key[:4] + "****"


class _LogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        s = get_settings()
        if s:
            for key in [
                s.OPENAI_COMPAT_API_KEY,
                s.effective_embedding_api_key,
                s.effective_llm_api_key,
            ]:
                if key and key in msg:
                    record.msg = record.msg.replace(key, _mask_key(key))
        return True


class Settings(BaseSettings):
    ARTICLE_SOURCE_DIR: str = ""
    DATA_DIR: str = "data"

    OPENAI_COMPAT_BASE_URL: str = ""
    OPENAI_COMPAT_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""
    LLM_MODEL: str = ""

    TOP_K: int = 8
    SIMILARITY_THRESHOLD: float = 0.5
    RAG_CONTEXT_TOKEN_BUDGET: int = 6000
    LOG_LEVEL: str = "INFO"

    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""

    VECTOR_STORE: str = "chroma"
    VECTOR_DISTANCE_METRIC: str = "cosine"
    EMBEDDING_MAX_TOKENS: int = 8191
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_REQUESTS_PER_MINUTE: int = 60
    CHUNK_TARGET_MIN_CHARS: int = 600
    CHUNK_TARGET_MAX_CHARS: int = 1000
    CHUNK_OVERLAP: int = 100
    MAX_OUTPUT_TOKENS: int = 2048
    CHAT_HISTORY_TURNS: int = 4
    LLM_CONTEXT_WINDOW: int = 32768

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def effective_embedding_base_url(self) -> str:
        return self.EMBEDDING_BASE_URL or self.OPENAI_COMPAT_BASE_URL

    @property
    def effective_embedding_api_key(self) -> str:
        return self.EMBEDDING_API_KEY or self.OPENAI_COMPAT_API_KEY

    @property
    def effective_llm_base_url(self) -> str:
        return self.LLM_BASE_URL or self.OPENAI_COMPAT_BASE_URL

    @property
    def effective_llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.OPENAI_COMPAT_API_KEY

    @property
    def chroma_dir(self) -> str:
        return os.path.join(self.DATA_DIR, "chroma")

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.DATA_DIR, "index_manifest.json")


def setup_logging(level: str | None = None) -> None:
    log_level = level or get_settings().LOG_LEVEL
    handler = logging.StreamHandler()
    handler.addFilter(_LogFilter())
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler],
    )


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
