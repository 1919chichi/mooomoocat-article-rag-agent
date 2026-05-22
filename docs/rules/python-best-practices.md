# Python 最佳实践规约

本文档基于 2026-05-22 重构中发现的 8 类问题，规定项目内禁止或必须遵守的编码模式。

---

## 1. 配置单例：禁止直接实例化 `Settings()`

**规则：** 业务代码中禁止直接使用 `Settings()`，必须调用 `get_settings()`。

**原因：** 每次 `Settings()` 都会重新读取环境变量并触发验证，丢失缓存，且可能在同一请求中产生不一致的配置状态。

**正确做法：**
```python
from mooomoocatrag.config import get_settings
settings = get_settings()
```

**错误做法：**
```python
from mooomoocatrag.config import Settings
settings = Settings()  # 禁止
```

---

## 2. 字符计数：不要将 overlap 重复加入 char_count

**规则：** 在分块逻辑中，`char_count` 只计算已提交 parts 的长度，不包含 overlap 文本。

**原因：** overlap 文本会被复用到下一个 chunk，若计入 char_count 会导致 chunk 提前截断，产生过短的分块。

**正确做法：**
```python
char_count = sum(len(p) for p in current_parts)
```

**错误做法：**
```python
char_count = sum(len(p) for p in current_parts) + (len(overlap_text) if overlap_text else 0)  # 禁止
```

---

## 3. Prompt 常量：单一来源原则

**规则：** 所有 LLM prompt 常量（system prompt、固定回复文本）必须定义在 `rag/prompt.py`，其他模块只能导入，不能本地重复定义。

**原因：** 重复定义导致修改时漏改，产生运行时行为不一致。

**正确做法：**
```python
from mooomoocatrag.rag.prompt import SYSTEM_PROMPT, INSUFFICIENT_CONTENT_RESPONSE
```

**错误做法：**
```python
# 在任意其他模块中本地定义相同字符串
INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"  # 禁止
```

---

## 4. 重试逻辑：使用 `retry_with_backoff`，禁止手写重试循环

**规则：** HTTP 调用的指数退避重试必须使用 `utils.retry_with_backoff`，禁止在各模块中各自实现重试循环。

**原因：** 手写重试循环难以统一测试，且容易出现退避策略不一致。

**正确做法：**
```python
from mooomoocatrag.utils import retry_with_backoff
result = retry_with_backoff(lambda: client.call(...))
```

**错误做法：**
```python
for attempt in range(4):  # 禁止：手写重试
    try:
        ...
    except Exception as e:
        time.sleep(...)
```

---

## 5. 外部客户端连接：使用 `cached_property`，禁止每次方法调用重新构造

**规则：** 类中的外部服务客户端（Qdrant、Elasticsearch、OpenAI 等）必须通过 `@cached_property` 实现，保证每个实例只创建一次连接。

**原因：** 每次方法调用都新建连接有性能损耗，且在高频调用场景下会耗尽连接池。

**正确做法：**
```python
from functools import cached_property

@dataclass
class MyStore:
    config: Settings

    @cached_property
    def _client(self):
        return SomeClient(url=self.config.URL)
```

**错误做法：**
```python
def _client(self):  # 禁止：每次调用都新建连接
    return SomeClient(url=self.config.URL)
```

---

## 6. 向后兼容别名：代码迁移完成后立即删除

**规则：** 为迁移目的创建的别名（如 `OldName = NewName`）必须在同一 PR 或下一 PR 中删除，禁止在代码库中长期存在。

**原因：** 别名命名混乱，增加代码库认知负担，且可能被外部代码意外依赖。

---

## 7. 共享工具函数：集中在 `utils.py`

**规则：** 跨模块复用的通用函数（token 估算、重试、格式化等）必须放在 `src/mooomoocatrag/utils.py`，禁止在各模块中各自实现。

**原因：** 分散实现的工具函数难以统一维护和测试。

**当前 `utils.py` 提供：**
- `estimate_tokens(text: str) -> int` — 中文 token 估算
- `is_retryable(error: Exception) -> bool` — HTTP 错误可重试判断
- `retry_with_backoff(fn, max_attempts=4) -> T` — 指数退避重试

---

## 8. 魔法数字：用具名变量表达语义

**规则：** 代码中不允许出现含义不明的数字字面量，必须用具名变量或注释说明语义。

**原因：** 魔法数字在修改时容易遗漏关联位置，且阅读时无法理解数字来源。

**正确做法：**
```python
source_lists = (dense_results, keyword_results)
num_sources = len(source_lists)
max_possible_score = num_sources * (1.0 / (rrf_k + 1))
```

**错误做法：**
```python
source_count = 2  # 禁止：2 从何而来？
max_possible_score = source_count * (1.0 / (rrf_k + 1))
```
