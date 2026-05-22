# 意图识别设计方案

**日期**：2026-05-22  
**状态**：已批准，待实现

---

## 背景与动机

当前系统对所有 query 强制走完整 RAG 检索流程，没有意图区分。主要痛点：

- 闲聊消息（"你好"、"谢谢"）走完整检索后返回"没有找到依据"，体验差
- 列举/总结类指令与普通问答处理方式相同，缺乏针对性响应
- 离题 query 浪费检索资源

---

## 意图类型

| 意图 | 说明 | 处理方式 |
|------|------|---------|
| `CHITCHAT` | 闲聊：问好、感谢、寒暄 | 小模型直接回复，无检索 |
| `OFF_TOPIC` | 与文章库完全无关的问题 | 固定模板拒绝，无检索 |
| `LIST` | 列举文章：列出/有哪些/所有 | manifest 元数据查询，返回文章列表 |
| `SUMMARIZE` | 总结某篇/某类文章 | RAG 检索 + 总结 prompt |
| `QA` | 问答（默认兜底） | 现有完整 RAG 流程 |

---

## 整体架构

```
chat_turn(query, history)
    │
    ▼
IntentRouter.classify(query, conversation_history)
    │  1. RuleClassifier   — 零成本，覆盖高置信度白名单 case
    │  2. LLMClassifier    — 仅当规则未命中时调用小模型
    │     （OFF_TOPIC 永远只走 LLM，不走规则）
    │
    ▼
IntentResult(type, confidence, method, raw_response, metadata)
    │
    ▼
IntentDispatcher.dispatch(...)
    ├── CHITCHAT   → handlers/chitchat.py   (小模型，无检索)
    ├── OFF_TOPIC  → handlers/off_topic.py  (固定模板，无检索)
    ├── LIST       → handlers/list.py       (manifest 元数据查询)
    ├── SUMMARIZE  → handlers/summarize.py  (RAG + 总结 prompt)
    └── QA         → handlers/qa.py         (现有完整 RAG 流程)
```

---

## 文件结构

```
src/mooomoocatrag/rag/
    intent/
        __init__.py
        types.py              # IntentType enum + IntentResult dataclass
        router.py             # IntentRouter（规则 + LLM 分类）
        handlers/
            __init__.py       # 统一注册表
            chitchat.py
            off_topic.py
            list.py
            summarize.py
            qa.py             # 现有 chat_turn 核心逻辑移入
    chat.py                   # 精简为调度入口
```

---

## 数据模型

```python
class IntentType(str, Enum):
    CHITCHAT   = "chitchat"
    OFF_TOPIC  = "off_topic"
    LIST       = "list"
    SUMMARIZE  = "summarize"
    QA         = "qa"          # 兜底默认

@dataclass
class IntentResult:
    intent:       IntentType
    confidence:   float                        # 0.0–1.0
    method:       Literal["rule", "llm", "fallback"]
    raw_response: str | None                   # LLM 原始输出，调试用
    metadata:     dict                         # 含 rule_id 等扩展字段
```

---

## IntentRouter 接口

```python
class IntentRouter:
    def classify(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> IntentResult: ...
    # 内部永不 raise；置信度不足时返回 QA + method="fallback"
```

**多轮上下文**：「谢谢」在第一轮是 CHITCHAT，在 RAG 回答后可能是感谢，需传入历史判断。

---

## 规则分类器（保守白名单）

| rule_id | 触发条件 | 判定 |
|---------|---------|------|
| `chitchat_greeting` | query ≤ 10字 且 token 命中白名单（你好/谢谢/再见/哈哈/早/晚安） | CHITCHAT |
| `list_articles` | 以"列举/列出/有哪些/所有"开头 且含"文章/讲/关于" | LIST |
| `summarize_articles` | 以"总结/摘要/概括"开头 | SUMMARIZE |
| OFF_TOPIC | **不设规则，永远交给 LLM** | — |

规则设计原则：
- 保守白名单，宁漏不误
- 每条规则有 `rule_id`，写入 `IntentResult.metadata` 供日志分析
- 输入先 normalize（去全角标点、统一空格）

---

## LLM 分类器

- `temperature=0`（保证可复现）
- Structured output，用 Pydantic 解析：`{"intent": "QA", "confidence": 0.85, "reason": "..."}`
- 解析失败或 `confidence < 0.6` → 降级 `QA + method="fallback"`
- 模型：优先 `INTENT_LLM_MODEL` 配置项，未配置则复用 `LLM_MODEL`

### Prompt 要点

- 每类意图 2 个中文 few-shot 正例
- CHITCHAT / OFF_TOPIC 各 1 个反例（易混淆的 case）
- 显式声明："不确定时返回 QA，confidence 设为 0.5 以下，不要猜测"

---

## 各 Handler 行为

| Intent | 数据源 | 回复方式 |
|--------|--------|---------|
| CHITCHAT | 无检索 | 小模型自由生成 |
| OFF_TOPIC | 无检索 | 固定模板：`"这个问题超出了猫笔刀文章库的范围。"` |
| LIST | manifest 元数据（title / source_rel_path） | 结构化文章列表 |
| SUMMARIZE | RAG 检索 | RAG + 总结 prompt（区别于问答 prompt） |
| QA | RAG 检索 | 现有完整流程 |

---

## 测试策略

1. **单元测试**：mock LLM，只测规则层，覆盖每条规则正例/反例/边界
2. **集成测试**：用 vcr/cassette 录制真实 LLM 调用，不在 CI 每次打真实 API
3. **golden dataset**：`tests/fixtures/intent_cases.json`，≥30条（query, 预期 intent, 预期 method）
4. **回归测试**：LLM 返回损坏格式 / confidence=0.4 时，必须降级 `QA + method="fallback"`
5. **监控**：`classify` 出口打结构化日志（intent, confidence, method, latency_ms）

---

## 配置项新增

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `INTENT_LLM_MODEL` | 意图分类用小模型 | 复用 `LLM_MODEL` |
| `INTENT_CONFIDENCE_THRESHOLD` | LLM 分类置信度下限 | `0.6` |
