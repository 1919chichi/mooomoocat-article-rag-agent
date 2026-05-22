# 最佳实践重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 8 处不符合最佳实践的代码，并新增 utils 工具模块与 prompt 模块整合，消除重复逻辑。

**Architecture:** 新增 `utils.py` 提供共享工具（token 估算、重试），扩展 `prompt.py` 为所有 prompt 常量/构建函数的单一来源，各原文件就地修复其余问题。

**Tech Stack:** Python 3.10+, pydantic-settings, openai SDK, qdrant-client, elasticsearch

---

## 文件变更索引

| 操作 | 文件 |
|------|------|
| 新建 | `src/mooomoocatrag/utils.py` |
| 新建 | `tests/test_utils.py` |
| 修改 | `src/mooomoocatrag/rag/prompt.py` |
| 修改 | `src/mooomoocatrag/ingest/indexer.py` |
| 修改 | `src/mooomoocatrag/ingest/chunker.py` |
| 修改 | `src/mooomoocatrag/rag/embeddings.py` |
| 修改 | `src/mooomoocatrag/rag/vector_store.py` |
| 修改 | `src/mooomoocatrag/rag/intent/handlers/qa.py` |
| 修改 | `src/mooomoocatrag/rag/intent/handlers/summarize.py` |
| 修改 | `src/mooomoocatrag/rag/chat.py` |
| 修改 | `src/mooomoocatrag/rag/retriever.py` |
| 修改 | `tests/test_chat.py` |
| 修改 | `tests/test_embeddings.py` |
| 新建 | `rules/python-best-practices.md` |

---

### Task 1: 新增 `utils.py` — 共享工具函数（TDD）

**Files:**
- Create: `src/mooomoocatrag/utils.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_utils.py`：

```python
from __future__ import annotations

import pytest

from mooomoocatrag.utils import estimate_tokens, is_retryable, retry_with_backoff


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_fifteen_chars(self):
        assert estimate_tokens("a" * 15) == 10  # ceil(15 / 1.5)

    def test_chinese_text(self):
        assert estimate_tokens("好" * 3) == 2  # ceil(3 / 1.5)


class TestIsRetryable:
    def test_429(self):
        assert is_retryable(Exception("rate limit 429")) is True

    def test_500(self):
        assert is_retryable(Exception("server error 500")) is True

    def test_502(self):
        assert is_retryable(Exception("bad gateway 502")) is True

    def test_503(self):
        assert is_retryable(Exception("service unavailable 503")) is True

    def test_504(self):
        assert is_retryable(Exception("gateway timeout 504")) is True

    def test_400_not_retryable(self):
        assert is_retryable(Exception("bad request 400")) is False

    def test_connection_error_not_retryable(self):
        assert is_retryable(Exception("connection refused")) is False


class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        result = retry_with_backoff(fn)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_429(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise Exception("429 Too Many Requests")
            return "ok"

        result = retry_with_backoff(fn)
        assert result == "ok"
        assert len(calls) == 3

    def test_does_not_retry_non_retryable(self):
        def fn():
            raise ValueError("invalid input")

        with pytest.raises(ValueError, match="invalid input"):
            retry_with_backoff(fn)

    def test_raises_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)

        def fn():
            raise Exception("503 Service Unavailable")

        with pytest.raises(Exception, match="503"):
            retry_with_backoff(fn)

    def test_custom_max_attempts(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise Exception("503")

        with pytest.raises(Exception):
            retry_with_backoff(fn, max_attempts=2)

        assert len(calls) == 2
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/cz/github-project/mooomoocat-article-rag-agent && python -m pytest tests/test_utils.py -v 2>&1 | head -20
```

预期：`ModuleNotFoundError: No module named 'mooomoocatrag.utils'`

- [ ] **Step 3: 实现 `utils.py`**

新建 `src/mooomoocatrag/utils.py`：

```python
from __future__ import annotations

import math
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 1.5)


def is_retryable(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "500" in msg or "502" in msg or "503" in msg or "504" in msg


def retry_with_backoff(fn: Callable[[], T], max_attempts: int = 4) -> T:
    wait_time = 1.0
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            if not is_retryable(e):
                raise
            time.sleep(wait_time)
            wait_time *= 2
    raise AssertionError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/test_utils.py -v
```

预期：所有测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/mooomoocatrag/utils.py tests/test_utils.py
git commit -m "feat: add utils module with estimate_tokens, is_retryable, retry_with_backoff"
```

---

### Task 2: 扩展 `prompt.py` — 新增 INSUFFICIENT_CONTENT_RESPONSE、SUMMARIZE_SYSTEM_PROMPT、build_summarize_prompt

**Files:**
- Modify: `src/mooomoocatrag/rag/prompt.py`
- Modify: `tests/test_prompt.py`

- [ ] **Step 1: 在 test_prompt.py 中添加失败测试**

在 `tests/test_prompt.py` 末尾追加：

```python
class TestSummarize:
    def test_insufficient_content_response_is_string(self):
        from mooomoocatrag.rag.prompt import INSUFFICIENT_CONTENT_RESPONSE
        assert isinstance(INSUFFICIENT_CONTENT_RESPONSE, str)
        assert "没有找到足够依据" in INSUFFICIENT_CONTENT_RESPONSE

    def test_build_summarize_prompt_returns_two_messages(self, sample_results):
        from mooomoocatrag.rag.prompt import build_summarize_prompt
        messages = build_summarize_prompt("总结一下猫的文章", sample_results)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_build_summarize_prompt_includes_chunks(self, sample_results):
        from mooomoocatrag.rag.prompt import build_summarize_prompt
        messages = build_summarize_prompt("总结", sample_results)
        user_content = messages[1]["content"]
        assert "[1]" in user_content
        assert "[2]" in user_content
        assert "This is a test article about cats" in user_content

    def test_build_summarize_prompt_includes_query(self, sample_results):
        from mooomoocatrag.rag.prompt import build_summarize_prompt
        query = "总结猫的生活习性"
        messages = build_summarize_prompt(query, sample_results)
        assert query in messages[1]["content"]
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_prompt.py::TestSummarize -v
```

预期：`ImportError` 或 `AssertionError`

- [ ] **Step 3: 更新 `prompt.py`**

将 `src/mooomoocatrag/rag/prompt.py` 改为：

```python
from __future__ import annotations

from mooomoocatrag.models import RetrievalResult

INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"

SYSTEM_PROMPT = """你是一个基于猫笔刀文章库回答问题的 Agent。
你必须优先依据给定的文章片段回答。
使用 [1]、[2] 等标记引用对应片段。
不要把没有出现在文章片段中的内容说成猫笔刀文章观点。
如果文章片段不足以回答，直接说明"当前猫笔刀文章库中没有找到足够依据"。"""

SUMMARIZE_SYSTEM_PROMPT = """你是一个基于猫笔刀文章库做内容总结的 Agent。
请根据给定的文章片段，对用户请求的内容进行结构化总结。
使用 [1]、[2] 等标记引用对应片段。
如果文章片段不足以支撑总结，说明"当前猫笔刀文章库中没有找到足够依据"。"""


def build_rag_prompt(
    query: str, results: list[RetrievalResult], history: list[dict] | None = None
) -> list[dict]:
    """构造 OpenAI Chat Completions 格式的 RAG prompt，包含 system 指令、检索片段和对话历史。"""
    messages: list[dict] = []
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    if results:
        context_parts = ["以下是检索到的文章片段：\n"]
        for i, result in enumerate(results, 1):
            context_parts.append(f"[{i}] {result.chunk.text}")
        context_parts.append("")
        context_parts.append(f"用户问题：{query}")
        context = "\n".join(context_parts)
    else:
        context = f"用户问题：{query}\n\n当前猫笔刀文章库中没有找到足够依据。"

    if history:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": context})
    return messages


def build_summarize_prompt(query: str, results: list[RetrievalResult]) -> list[dict]:
    context_parts = ["以下是检索到的文章片段：\n"]
    for i, result in enumerate(results, 1):
        context_parts.append(f"[{i}] {result.chunk.text}")
    context_parts.append(f"\n用户请求：{query}")
    return [
        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(context_parts)},
    ]


def format_citations(results: list[RetrievalResult]) -> list[str]:
    """由程序生成引用列表，不依赖 LLM，避免 LLM 伪造或遗漏引用。"""
    citations: list[str] = []
    for i, result in enumerate(results, 1):
        heading = result.chunk.nearest_heading
        heading_part = f"小标题：{heading}" if heading else "小标题：无"
        citation = (
            f"[{i}] {result.chunk.title} | {result.chunk.source_rel_path} | "
            f"chunk {result.chunk.chunk_index} | {heading_part}"
        )
        citations.append(citation)
    return citations
```

- [ ] **Step 4: 运行全部 prompt 测试**

```bash
python -m pytest tests/test_prompt.py -v
```

预期：所有测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/mooomoocatrag/rag/prompt.py tests/test_prompt.py
git commit -m "feat(prompt): add INSUFFICIENT_CONTENT_RESPONSE, SUMMARIZE_SYSTEM_PROMPT, build_summarize_prompt"
```

---

### Task 3: 修复 `indexer.py` — 替换 `Settings()` 为 `get_settings()`

**Files:**
- Modify: `src/mooomoocatrag/ingest/indexer.py:45-87`

- [ ] **Step 1: 运行现有测试确认基线**

```bash
python -m pytest tests/test_indexer.py -v
```

预期：全部 PASS（记录当前状态）

- [ ] **Step 2: 修改 `load_manifest`**

将 `src/mooomoocatrag/ingest/indexer.py` 的 `load_manifest` 函数改为：

```python
def load_manifest(data_dir: str) -> IndexManifest:
    """从 manifest 文件加载索引状态；文件不存在时返回空 manifest（使用当前配置默认值）。"""
    from mooomoocatrag.config import get_settings
    manifest_path = Path(data_dir) / "index_manifest.json"

    if not manifest_path.exists():
        settings = get_settings()
        return IndexManifest(
            schema_version=1,
            source_root="",
            vector_store=settings.VECTOR_STORE,
            keyword_store=settings.KEYWORD_STORE,
            retrieval_mode=settings.RETRIEVAL_MODE,
            vector_distance_metric=settings.VECTOR_DISTANCE_METRIC,
            embedding_provider="openai-compatible",
            embedding_model="",
            embedding_dimension=0,
            qdrant_collection=settings.QDRANT_COLLECTION,
            elasticsearch_index=settings.ELASTICSEARCH_INDEX,
            chunker_config=default_chunker_config(settings),
            articles={},
        )

    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    settings = get_settings()
    return IndexManifest(
        schema_version=data.get("schema_version", 1),
        source_root=data.get("source_root", ""),
        vector_store=data.get("vector_store", settings.VECTOR_STORE),
        keyword_store=data.get("keyword_store", settings.KEYWORD_STORE),
        retrieval_mode=data.get("retrieval_mode", settings.RETRIEVAL_MODE),
        vector_distance_metric=data.get(
            "vector_distance_metric", settings.VECTOR_DISTANCE_METRIC
        ),
        embedding_provider=data.get("embedding_provider", "openai-compatible"),
        embedding_model=data.get("embedding_model", ""),
        embedding_dimension=data.get("embedding_dimension", 0),
        qdrant_collection=data.get("qdrant_collection", settings.QDRANT_COLLECTION),
        elasticsearch_index=data.get(
            "elasticsearch_index",
            settings.ELASTICSEARCH_INDEX,
        ),
        chunker_config=data.get("chunker_config", {}),
        articles=data.get("articles", {}),
    )
```

同时移除顶部不再需要的 `from mooomoocatrag.config import Settings`（如 `Settings` 在其他地方仍被用到则保留）。检查：`indexer.py` 中 `Settings` 只在 `load_manifest` 里用到，其余函数接收 `settings: Settings` 参数，所以 `Settings` 类型注解仍需保留。

最终 import 行：
```python
from mooomoocatrag.config import Settings, get_settings
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_indexer.py -v
```

预期：全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/mooomoocatrag/ingest/indexer.py
git commit -m "fix(indexer): replace raw Settings() with get_settings() singleton in load_manifest"
```

---

### Task 4: 修复 `chunker.py` — 消除 `char_count` 对 `overlap_text` 的重复计数

**Files:**
- Modify: `src/mooomoocatrag/ingest/chunker.py:190`

- [ ] **Step 1: 运行现有测试确认基线**

```bash
python -m pytest tests/test_chunker.py -v
```

预期：全部 PASS

- [ ] **Step 2: 修改 `_split_long_section`**

在 `src/mooomoocatrag/ingest/chunker.py` 中，找到第 190 行：

```python
    char_count = sum(len(p) for p in current_parts) + (len(overlap_text) if overlap_text else 0)
```

替换为：

```python
    char_count = sum(len(p) for p in current_parts)
```

说明：`overlap_text` 已在上方 `current_parts = [overlap_text]` 时放入列表，`sum(len(p) for p in current_parts)` 已包含其长度，再加一次会导致字符预算估算偏高。

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_chunker.py -v
```

预期：全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/mooomoocatrag/ingest/chunker.py
git commit -m "fix(chunker): remove double-count of overlap_text in _split_long_section char_count"
```

---

### Task 5: 重构 `embeddings.py` — 使用 `retry_with_backoff`

**Files:**
- Modify: `src/mooomoocatrag/rag/embeddings.py`
- Modify: `tests/test_embeddings.py`

- [ ] **Step 1: 更新 `test_embeddings.py`**

`_is_retryable` 已移入 `utils.py`（重命名为 `is_retryable`），retry 的 `time.sleep` 现在在 `utils.py` 中。需要更新两处：

1. 修改 import（移除 `_is_retryable`，改为从 utils 导入）
2. 修改重试测试的 patch 路径

将 `tests/test_embeddings.py` 顶部 import 改为：

```python
from mooomoocatrag.rag.embeddings import _batch, embed_texts
from mooomoocatrag.utils import is_retryable
```

将 `TestIsRetryable` 类的测试改为使用 `is_retryable`（从 utils 导入）：

```python
class TestIsRetryable:
    def test_retryable_429(self):
        assert is_retryable(Exception("error 429")) is True

    def test_retryable_500(self):
        assert is_retryable(Exception("error 500")) is True

    def test_retryable_502(self):
        assert is_retryable(Exception("error 502")) is True

    def test_retryable_503(self):
        assert is_retryable(Exception("error 503")) is True

    def test_retryable_504(self):
        assert is_retryable(Exception("error 504")) is True

    def test_not_retryable(self):
        assert is_retryable(Exception("connection error")) is False
```

将重试相关测试的 `@patch("mooomoocatrag.rag.embeddings.time.sleep")` 改为 `@patch("mooomoocatrag.utils.time.sleep")`：

```python
    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    @patch("mooomoocatrag.utils.time.sleep")   # <-- 从 embeddings 改为 utils
    def test_retry_on_429(self, mock_sleep, mock_openai_class):
        ...

    @patch("mooomoocatrag.rag.embeddings.OpenAI")
    @patch("mooomoocatrag.utils.time.sleep")   # <-- 同上
    def test_retry_on_500(self, mock_sleep, mock_openai_class):
        ...
```

注意：`test_rate_limiting` 测试（批次间限速 sleep）保持 `@patch("mooomoocatrag.rag.embeddings.time.sleep")`，因为该 sleep 仍在 `embeddings.py` 的 `embed_texts` 方法中。

- [ ] **Step 2: 确认测试失败（旧实现不匹配新 patch）**

```bash
python -m pytest tests/test_embeddings.py -v 2>&1 | head -30
```

预期：`TestIsRetryable` 的导入失败，retry 测试 patch 失败。

- [ ] **Step 3: 重写 `embeddings.py`**

将 `src/mooomoocatrag/rag/embeddings.py` 改为：

```python
from __future__ import annotations

import time
import logging
from typing import Iterator

import httpx
from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.utils import is_retryable, retry_with_backoff

logger = logging.getLogger(__name__)


class EmbeddingStrategy:
    def embed_texts(self, texts: list[str], config: Settings) -> list[list[float]]:
        raise NotImplementedError


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
    return retry_with_backoff(
        lambda: [item.embedding for item in client.embeddings.create(model=model, input=texts).data]
    )


class VolcengineEmbeddingStrategy(EmbeddingStrategy):
    """Volcengine ARK /embeddings/multimodal endpoint."""

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
        return retry_with_backoff(lambda: self._call_api(url, api_key, text, model))

    @staticmethod
    def _call_api(url: str, api_key: str, text: str, model: str) -> list[float]:
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


_VALID_PROVIDERS = ("openai", "volcengine")


def get_embedding_strategy(config: Settings) -> EmbeddingStrategy:
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


def embed_texts(texts: list[str], config: Settings) -> list[list[float]]:
    strategy = get_embedding_strategy(config)
    return strategy.embed_texts(texts, config)
```

注意：移除了 `abc` 模块和 `@abc.abstractmethod`（改用普通 `raise NotImplementedError`），移除了 `_is_retryable`。

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_embeddings.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/mooomoocatrag/rag/embeddings.py tests/test_embeddings.py
git commit -m "refactor(embeddings): extract retry logic to utils.retry_with_backoff, remove duplicated _is_retryable"
```

---

### Task 6: 重构 `vector_store.py` — `cached_property` 连接复用

**Files:**
- Modify: `src/mooomoocatrag/rag/vector_store.py`

- [ ] **Step 1: 运行现有测试确认基线**

```bash
python -m pytest tests/test_vector_store.py -v
```

预期：全部 PASS

- [ ] **Step 2: 更新 `QdrantVectorStore`**

在 `src/mooomoocatrag/rag/vector_store.py` 中，import 区域添加：

```python
from functools import cached_property
```

将 `QdrantVectorStore` 类改为（`_client` 方法变属性，`_ensure_collection` 移除 `client` 参数）：

```python
@dataclass
class QdrantVectorStore(DenseStore):
    config: Settings

    @cached_property
    def _client(self):
        _require_dependency("qdrant-client", QdrantClient)
        kwargs = {"url": self.config.QDRANT_URL}
        if self.config.QDRANT_API_KEY:
            kwargs["api_key"] = self.config.QDRANT_API_KEY
        return QdrantClient(**kwargs)

    def _ensure_collection(self, embedding_dimension: int) -> None:
        """若 Qdrant collection 不存在则创建，已存在则跳过（幂等操作）。"""
        if bool(self._client.collection_exists(self.config.QDRANT_COLLECTION)):
            return
        self._client.create_collection(
            collection_name=self.config.QDRANT_COLLECTION,
            vectors_config=qdrant_models.VectorParams(
                size=embedding_dimension,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[ChunkMeta], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        self._ensure_collection(chunks[0].embedding_dimension)
        points = [
            qdrant_models.PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "chunk_index": chunk.chunk_index,
                    "nearest_heading": chunk.nearest_heading,
                    "source_rel_path": chunk.source_rel_path,
                    "title": chunk.title,
                    "content_hash": chunk.content_hash,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimension": chunk.embedding_dimension,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]
        self._client.upsert(
            collection_name=self.config.QDRANT_COLLECTION,
            points=points,
            wait=True,
        )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self._client.delete(
            collection_name=self.config.QDRANT_COLLECTION,
            points_selector=qdrant_models.PointIdsList(points=chunk_ids),
            wait=True,
        )

    def query_dense(self, query_vector: list[float], top_k: int) -> list[dict]:
        results = self._client.search(
            collection_name=self.config.QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        candidates: list[dict] = []
        for point in results:
            payload = dict(point.payload or {})
            candidates.append(
                {
                    "chunk_id": str(point.id),
                    "score": float(point.score),
                    "metadata": payload,
                    "document": payload.get("text", ""),
                    "source": "dense",
                }
            )
        return candidates

    def clear(self) -> None:
        if self._client.collection_exists(self.config.QDRANT_COLLECTION):
            self._client.delete_collection(self.config.QDRANT_COLLECTION)
```

- [ ] **Step 3: 更新 `ElasticsearchKeywordStore`**

将 `ElasticsearchKeywordStore` 类改为（同样 `_client` 改为 `cached_property`，`_ensure_index` 移除 `client` 参数）：

```python
@dataclass
class ElasticsearchKeywordStore(KeywordStore):
    config: Settings

    @cached_property
    def _client(self):
        _require_dependency("elasticsearch", Elasticsearch)
        kwargs: dict = {"hosts": [self.config.ELASTICSEARCH_URL]}
        if self.config.ELASTICSEARCH_API_KEY:
            kwargs["api_key"] = self.config.ELASTICSEARCH_API_KEY
        elif self.config.ELASTICSEARCH_USERNAME or self.config.ELASTICSEARCH_PASSWORD:
            kwargs["basic_auth"] = (
                self.config.ELASTICSEARCH_USERNAME,
                self.config.ELASTICSEARCH_PASSWORD,
            )
        if self.config.ELASTICSEARCH_CA_CERT_PATH:
            kwargs["ca_certs"] = self.config.ELASTICSEARCH_CA_CERT_PATH
        return Elasticsearch(**kwargs)

    def _ensure_index(self) -> None:
        """若 ES index 不存在则创建并设置 mapping，已存在则跳过（幂等操作）。"""
        if self._client.indices.exists(index=self.config.ELASTICSEARCH_INDEX):
            return
        self._client.indices.create(
            index=self.config.ELASTICSEARCH_INDEX,
            mappings={
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "article_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "title": {"type": "text", "analyzer": self.config.ELASTICSEARCH_ANALYZER},
                    "nearest_heading": {
                        "type": "text",
                        "analyzer": self.config.ELASTICSEARCH_ANALYZER,
                    },
                    "source_rel_path": {"type": "keyword"},
                    "content_hash": {"type": "keyword"},
                    "embedding_model": {"type": "keyword"},
                    "embedding_dimension": {"type": "integer"},
                    "text": {"type": "text", "analyzer": self.config.ELASTICSEARCH_ANALYZER},
                }
            },
        )

    def upsert_chunks(self, chunks: list[ChunkMeta]) -> None:
        if not chunks:
            return
        self._ensure_index()
        actions = [
            {
                "_op_type": "index",
                "_index": self.config.ELASTICSEARCH_INDEX,
                "_id": chunk.chunk_id,
                "_source": {
                    "chunk_id": chunk.chunk_id,
                    "article_id": chunk.article_id,
                    "chunk_index": chunk.chunk_index,
                    "nearest_heading": chunk.nearest_heading,
                    "source_rel_path": chunk.source_rel_path,
                    "title": chunk.title,
                    "content_hash": chunk.content_hash,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimension": chunk.embedding_dimension,
                    "text": chunk.text,
                },
            }
            for chunk in chunks
        ]
        helpers.bulk(self._client, actions)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self._client.delete_by_query(
            index=self.config.ELASTICSEARCH_INDEX,
            query={"terms": {"chunk_id": chunk_ids}},
            refresh=True,
        )

    def query_keyword(self, query: str, top_k: int) -> list[dict]:
        response = self._client.search(
            index=self.config.ELASTICSEARCH_INDEX,
            size=top_k,
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "nearest_heading^2", "text"],
                }
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        candidates: list[dict] = []
        for hit in hits:
            source = dict(hit.get("_source", {}))
            candidates.append(
                {
                    "chunk_id": source.get("chunk_id", hit.get("_id", "")),
                    "score": float(hit.get("_score") or 0.0),
                    "metadata": source,
                    "document": source.get("text", ""),
                    "source": "keyword",
                }
            )
        return candidates

    def clear(self) -> None:
        if self._client.indices.exists(index=self.config.ELASTICSEARCH_INDEX):
            self._client.indices.delete(index=self.config.ELASTICSEARCH_INDEX)
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_vector_store.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/mooomoocatrag/rag/vector_store.py
git commit -m "refactor(vector_store): use cached_property for _client, reuse connection within store instance"
```

---

### Task 7: 更新 `qa.py` — 使用 `prompt.SYSTEM_PROMPT` 和 `utils.estimate_tokens`

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/handlers/qa.py`

- [ ] **Step 1: 运行现有测试确认基线**

```bash
python -m pytest tests/test_chat.py -v
```

预期：全部 PASS（先确认基线，后续步骤会改 import）

- [ ] **Step 2: 更新 `qa.py`**

将 `src/mooomoocatrag/rag/intent/handlers/qa.py` 改为：

```python
from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import (
    INSUFFICIENT_CONTENT_RESPONSE,
    SYSTEM_PROMPT,
    build_rag_prompt,
    format_citations,
)
from mooomoocatrag.rag.retriever import retrieve
from mooomoocatrag.utils import estimate_tokens

_VALID_HISTORY_ROLES = {"user", "assistant"}


def _recent_valid_history(history: list[dict], max_messages: int) -> list[dict]:
    valid = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in history
        if turn.get("role", "user") in _VALID_HISTORY_ROLES
    ]
    return valid[-max_messages:] if max_messages > 0 else []


def handle_qa(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    results = retrieve(query, config, manifest)
    if not results:
        return ChatResponse(
            answer=INSUFFICIENT_CONTENT_RESPONSE,
            citations=[],
            retrieved_count=0,
            intent="qa",
        )

    input_token_budget = config.LLM_CONTEXT_WINDOW - config.MAX_OUTPUT_TOKENS
    system_prompt_tokens = estimate_tokens(SYSTEM_PROMPT)

    max_history_messages = config.CHAT_HISTORY_TURNS * 2
    trimmed_history = _recent_valid_history(history, max_history_messages)
    adjusted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

    retrieved_tokens = sum(estimate_tokens(r.chunk.text) for r in adjusted_results)
    query_tokens = estimate_tokens(query)
    history_tokens = sum(estimate_tokens(t.get("content", "")) for t in trimmed_history)
    total_estimated = system_prompt_tokens + retrieved_tokens + query_tokens + history_tokens

    if total_estimated > input_token_budget:
        for keep_count in range(len(adjusted_results), 0, -1):
            test_results = adjusted_results[:keep_count]
            test_tokens = sum(estimate_tokens(r.chunk.text) for r in test_results)
            test_total = system_prompt_tokens + test_tokens + query_tokens + history_tokens
            if test_total <= input_token_budget:
                adjusted_results = test_results
                break
        else:
            adjusted_results = adjusted_results[:1]

    messages = build_rag_prompt(query, adjusted_results, trimmed_history)
    client = OpenAI(
        base_url=config.effective_llm_base_url,
        api_key=config.effective_llm_api_key,
    )
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        max_tokens=config.MAX_OUTPUT_TOKENS,
    )
    answer = response.choices[0].message.content or ""
    return ChatResponse(
        answer=answer,
        citations=format_citations(adjusted_results),
        retrieved_count=len(adjusted_results),
        intent="qa",
    )
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_chat.py -v
```

预期：全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/mooomoocatrag/rag/intent/handlers/qa.py
git commit -m "refactor(qa): use prompt.SYSTEM_PROMPT and utils.estimate_tokens, remove inline duplicates"
```

---

### Task 8: 更新 `summarize.py` — 使用 prompt 模块

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/handlers/summarize.py`

- [ ] **Step 1: 将 `summarize.py` 改为**

```python
from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import (
    INSUFFICIENT_CONTENT_RESPONSE,
    build_summarize_prompt,
    format_citations,
)
from mooomoocatrag.rag.retriever import retrieve


def handle_summarize(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    results = retrieve(query, config, manifest)
    if not results:
        return ChatResponse(
            answer=INSUFFICIENT_CONTENT_RESPONSE,
            citations=[],
            retrieved_count=0,
            intent="summarize",
        )

    messages = build_summarize_prompt(query, results)
    client = OpenAI(
        base_url=config.effective_llm_base_url,
        api_key=config.effective_llm_api_key,
    )
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        max_tokens=config.MAX_OUTPUT_TOKENS,
    )
    answer = response.choices[0].message.content or ""
    return ChatResponse(
        answer=answer,
        citations=format_citations(results),
        retrieved_count=len(results),
        intent="summarize",
    )
```

- [ ] **Step 2: 运行全量测试**

```bash
python -m pytest tests/ -v --tb=short
```

预期：全部 PASS

- [ ] **Step 3: 提交**

```bash
git add src/mooomoocatrag/rag/intent/handlers/summarize.py
git commit -m "refactor(summarize): use prompt.build_summarize_prompt, remove inline _SUMMARIZE_SYSTEM and _NO_CONTENT"
```

---

### Task 9: 清理 `chat.py` alias，更新 `test_chat.py` 导入

**Files:**
- Modify: `src/mooomoocatrag/rag/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: 更新 `chat.py`**

将 `src/mooomoocatrag/rag/chat.py` 改为：

```python
from __future__ import annotations

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.intent import IntentRouter, IntentType
from mooomoocatrag.rag.intent.handlers import (
    handle_chitchat,
    handle_list,
    handle_off_topic,
    handle_qa,
    handle_summarize,
)


def chat_turn(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    """Route a single conversation turn to the appropriate handler based on intent."""
    router = IntentRouter(config)
    intent_result = router.classify(query, history)

    if intent_result.intent == IntentType.CHITCHAT:
        return handle_chitchat(query, history, config)
    if intent_result.intent == IntentType.OFF_TOPIC:
        return handle_off_topic()
    if intent_result.intent == IntentType.LIST:
        return handle_list(query, manifest)
    if intent_result.intent == IntentType.SUMMARIZE:
        return handle_summarize(query, history, config, manifest)
    return handle_qa(query, history, config, manifest)
```

- [ ] **Step 2: 更新 `test_chat.py` 导入**

将 `tests/test_chat.py` 第 10 行：

```python
from mooomoocatrag.rag.chat import chat_turn, NO_INSUFFICIENT_CONTENTResponse
```

改为：

```python
from mooomoocatrag.rag.chat import chat_turn
from mooomoocatrag.rag.intent.handlers import INSUFFICIENT_CONTENT_RESPONSE
```

将第 124 行：

```python
        assert response.answer == NO_INSUFFICIENT_CONTENTResponse
```

改为：

```python
        assert response.answer == INSUFFICIENT_CONTENT_RESPONSE
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_chat.py -v
```

预期：全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/mooomoocatrag/rag/chat.py tests/test_chat.py
git commit -m "refactor(chat): remove NO_INSUFFICIENT_CONTENTResponse alias, update test to import from handlers"
```

---

### Task 10: 修复 `retriever.py` — 消除魔法数字 `source_count = 2`

**Files:**
- Modify: `src/mooomoocatrag/rag/retriever.py:165-166`

- [ ] **Step 1: 运行现有测试确认基线**

```bash
python -m pytest tests/test_retriever.py -v
```

预期：全部 PASS

- [ ] **Step 2: 修改 `_fuse_candidates`**

在 `src/mooomoocatrag/rag/retriever.py` 中，找到 `_fuse_candidates` 函数内的循环和归一化逻辑，将：

```python
    for source_results in (dense_results, keyword_results):
        for rank, candidate in enumerate(source_results, start=1):
```

和：

```python
    # 归一化基准：两路都在第 1 名时的理论最大分数
    source_count = 2
    max_possible_score = source_count * (1.0 / (rrf_k + 1))
```

改为：

```python
    source_lists = (dense_results, keyword_results)
    for source_results in source_lists:
        for rank, candidate in enumerate(source_results, start=1):
```

和：

```python
    num_sources = len(source_lists)
    max_possible_score = num_sources * (1.0 / (rrf_k + 1))
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_retriever.py -v
```

预期：全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/mooomoocatrag/rag/retriever.py
git commit -m "refactor(retriever): derive num_sources from source_lists, remove magic number"
```

---

### Task 11: 新建 `rules/` 目录 — 项目规约

**Files:**
- Create: `rules/python-best-practices.md`

- [ ] **Step 1: 创建规约文件**

新建 `rules/python-best-practices.md`（内容见规约设计）

- [ ] **Step 2: 运行全量测试确认无回归**

```bash
python -m pytest tests/ -v --tb=short
```

预期：全部 PASS

- [ ] **Step 3: 提交**

```bash
git add rules/
git commit -m "docs(rules): add python-best-practices project conventions"
```

---

## 自检

**Spec 覆盖：**
- [x] Issue 1 (indexer.py Settings singleton) → Task 3
- [x] Issue 2 (chunker.py char_count bug) → Task 4
- [x] Issue 3 (qa.py SYSTEM_PROMPT duplicate) → Task 7
- [x] Issue 4 (summarize.py _NO_CONTENT duplicate) → Task 8
- [x] Issue 5 (embeddings.py retry duplication) → Task 5
- [x] Issue 6 (vector_store.py new client per call) → Task 6
- [x] Issue 7 (chat.py alias NO_INSUFFICIENT_CONTENTResponse) → Task 9
- [x] Issue 8 (retriever.py source_count magic number) → Task 10
- [x] utils.py 新增 → Task 1
- [x] prompt.py 整合 → Task 2
- [x] rules/ 规约 → Task 11

**Placeholder 扫描：** 无 TBD/TODO/fill-in-details。

**类型一致性：**
- `retry_with_backoff` 在 Task 1 定义，Task 5 使用 — 签名一致
- `estimate_tokens` 在 Task 1 定义，Task 7 使用 — 签名一致
- `INSUFFICIENT_CONTENT_RESPONSE` 在 Task 2 迁移到 `prompt.py`，Task 7/8/9 使用 — 路径一致
- `build_summarize_prompt` 在 Task 2 定义，Task 8 使用 — 签名一致
