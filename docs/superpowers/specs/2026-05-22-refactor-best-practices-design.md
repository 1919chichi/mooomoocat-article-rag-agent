# 重构规格：消除最佳实践偏差

**日期：** 2026-05-22  
**方案：** B+C（精准修复 + utils 工具模块 + prompt 模块整合）

---

## 问题清单

| # | 文件 | 问题 | 类型 |
|---|------|------|------|
| 1 | `ingest/indexer.py` | `load_manifest` 直接调用 `Settings()` 6 次绕过单例 | Bug-adjacent |
| 2 | `ingest/chunker.py` | `_split_long_section` 中 `char_count` 对 `overlap_text` 重复计数 | 潜在 bug |
| 3 | `rag/intent/handlers/qa.py` | inline system prompt 与 `prompt.py:SYSTEM_PROMPT` 完全重复 | DRY |
| 4 | `rag/intent/handlers/summarize.py` | `_NO_CONTENT` 与 `qa.py:INSUFFICIENT_CONTENT_RESPONSE` 重复 | DRY |
| 5 | `rag/embeddings.py` | 两个 strategy 各自实现几乎相同的指数退避重试逻辑 | DRY |
| 6 | `rag/vector_store.py` | 每次方法调用都新建 Qdrant/ES 客户端连接 | 性能 |
| 7 | `rag/chat.py` | alias `NO_INSUFFICIENT_CONTENTResponse` 命名混乱，已无迁移必要 | 代码异味 |
| 8 | `rag/retriever.py` | `source_count = 2` 硬编码魔法数字 | 可读性 |

---

## 架构

### 新增：`src/mooomoocatrag/utils.py`

共享工具函数，所有模块均可引入：

- `estimate_tokens(text: str) -> int` — 中文 token 估算（`ceil(len/1.5)`）
- `is_retryable(error: Exception) -> bool` — 判断 HTTP 错误是否可重试（429/5xx）
- `retry_with_backoff(fn, max_attempts=4) -> T` — 通用指数退避重试装饰器

### 变更：`rag/prompt.py` — Prompt 单一来源

新增内容：
- `INSUFFICIENT_CONTENT_RESPONSE: str` — 无内容时的固定回复文本
- `SUMMARIZE_SYSTEM_PROMPT: str` — 总结场景的 system prompt
- `build_summarize_prompt(query, results) -> list[dict]` — 构建总结 prompt 消息列表

保留现有：`SYSTEM_PROMPT`、`build_rag_prompt`、`format_citations`

### 变更：`rag/embeddings.py`

- 删除 `_is_retryable`（移入 utils）
- `_embed_batch_with_retry` 改为调用 `retry_with_backoff`（3 行 → 1 行）
- `VolcengineEmbeddingStrategy._embed_with_retry` 同样改为调用 `retry_with_backoff`

### 变更：`rag/vector_store.py`

- `QdrantVectorStore._client()` 改为 `@cached_property`，删除 `client=None` 参数
- `ElasticsearchKeywordStore._client()` 同上
- 所有 `self._client()` 调用改为 `self._client`（属性访问）
- 每个 store 实例内客户端连接只创建一次

### 变更：`ingest/indexer.py`

- `load_manifest` 顶部调用一次 `settings = get_settings()`
- 删除所有 `Settings()` 直接实例化

### 变更：`ingest/chunker.py`

- `_split_long_section` 第 190 行：`char_count = sum(len(p) for p in current_parts)` 
  （删除重复计算 `+ (len(overlap_text) if overlap_text else 0)`）

### 变更：`rag/intent/handlers/qa.py`

- 导入 `SYSTEM_PROMPT`, `INSUFFICIENT_CONTENT_RESPONSE` 自 `rag.prompt`
- 导入 `estimate_tokens` 自 `utils`
- 删除内联 system prompt 字符串

### 变更：`rag/intent/handlers/summarize.py`

- 导入 `INSUFFICIENT_CONTENT_RESPONSE`, `build_summarize_prompt` 自 `rag.prompt`
- 删除 `_NO_CONTENT`, `_SUMMARIZE_SYSTEM` 本地常量
- `handle_summarize` 使用 `build_summarize_prompt` 构建消息

### 变更：`rag/chat.py`

- 删除 `NO_INSUFFICIENT_CONTENTResponse` alias 及其注释

### 变更：`tests/test_chat.py`

- 导入改为 `from mooomoocatrag.rag.intent.handlers import INSUFFICIENT_CONTENT_RESPONSE`

### 变更：`rag/retriever.py`

- `source_count = 2` → `num_sources = len((dense_results, keyword_results))`（或直接 `= 2` 配合注释说明语义）

---

## 数据流（变更后）

```
QA/Summarize handler
  ├── prompt.py → SYSTEM_PROMPT / INSUFFICIENT_CONTENT_RESPONSE
  ├── utils.py  → estimate_tokens / retry_with_backoff
  └── (no local constants)

embeddings.py
  └── utils.py  → retry_with_backoff / is_retryable

vector_store.py
  └── cached_property → single client per store instance

indexer.py
  └── get_settings() → singleton (no raw Settings())
```

---

## 测试影响

- `test_chat.py`：更新一处 import，行为不变
- `test_vector_store.py`：`@patch("...QdrantClient")` 仍有效，`cached_property` 首次访问触发构造
- 其余测试：无影响

---

## 新增：`rules/` 目录

将 8 类问题写成项目规约，防止同类问题复现。
