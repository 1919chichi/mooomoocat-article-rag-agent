## 1. 数据模型与配置

- [ ] 1.1 新增 `IntentDecision` dataclass，字段包括 `intent`、`normalized_query`、`response` 和 `reason`。
- [ ] 1.2 给 `ChatResponse` 增加向后兼容的 `intent` 字段。
- [ ] 1.3 在 `Settings` 中新增 `ENABLE_INTENT_RECOGNITION: bool = True`。

## 2. 意图分类器

- [ ] 2.1 新增 `src/mooomoocatrag/rag/intent.py`，实现确定性的规则分类。
- [ ] 2.2 按顺序实现 `empty_or_invalid`、`control_command`、`chitchat`、`clarification_needed`，并把其他输入默认为 `rag_query`。
- [ ] 2.3 为非 RAG 意图增加本地回复文案。
- [ ] 2.4 增加单元测试，覆盖所有支持的意图和重复分类稳定性。

## 3. Chat 集成

- [ ] 3.1 在 `ENABLE_INTENT_RECOGNITION` 为 true 时，让 `chat_turn` 先分类输入。
- [ ] 3.2 对非 RAG 意图返回本地 `ChatResponse`，且不调用 retrieval 或 OpenAI。
- [ ] 3.3 保留 `rag_query` 的现有“先检索、再回答”行为。
- [ ] 3.4 增加 chat 测试，覆盖澄清/闲聊 bypass、`rag_query` 检索，以及关闭配置后的回退行为。

## 4. Search CLI 集成

- [ ] 4.1 在意图识别开启时，让 `search` 先分类输入，再做 embedding 配置校验和 manifest 加载。
- [ ] 4.2 对非 RAG 的 search 输入打印本地说明并成功退出。
- [ ] 4.3 保留 `rag_query` 的现有 search 输出和校验路径。
- [ ] 4.4 增加 CLI 测试，覆盖 `/help` bypass、正常 search 行为，以及关闭配置后的回退行为。

## 5. 验证

- [ ] 5.1 运行 `python -m pytest -q`。
- [ ] 5.2 运行 `python -m compileall -q src tests`。
- [ ] 5.3 运行 `mooomoocatrag --help`，确认 CLI 入口仍可加载。
