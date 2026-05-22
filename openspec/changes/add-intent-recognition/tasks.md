## 1. 数据模型与配置

- [x] 1.1 新增意图结果数据对象；实际实现为 `src/mooomoocatrag/rag/intent/types.py` 中的 `IntentResult`，字段包括 `intent`、`confidence`、`method`、`raw_response` 和 `metadata`。
- [x] 1.2 给 `ChatResponse` 增加向后兼容的 `intent` 字段。
- [ ] 1.3 在 `Settings` 中新增 `ENABLE_INTENT_RECOGNITION: bool = True`。当前实现已新增 `INTENT_LLM_MODEL` 和 `INTENT_CONFIDENCE_THRESHOLD`，但尚无总开关。

## 2. 意图分类器

- [x] 2.1 新增意图识别模块；实际实现为 `src/mooomoocatrag/rag/intent/` package，并在 `router.py` 中实现规则分类与 LLM fallback。
- [ ] 2.2 按顺序实现 `empty_or_invalid`、`control_command`、`chitchat`、`clarification_needed`，并把其他输入默认为 `rag_query`。当前实现覆盖 `chitchat`、`list`、`summarize`、`off_topic`、`qa`，未按原任务实现空输入、控制命令和澄清意图。
- [x] 2.3 为非 QA 意图增加本地或专用回复文案，覆盖 `chitchat`、`off_topic`、`list` 和 `summarize` handlers。
- [x] 2.4 增加单元测试和 golden dataset，覆盖规则分类、LLM fallback、list handler 和规则分类稳定性。

## 3. Chat 集成

- [x] 3.1 让 `chat_turn` 先通过 `IntentRouter` 分类输入；当前实现未提供 `ENABLE_INTENT_RECOGNITION` 总开关。
- [x] 3.2 对非 QA 意图返回对应 `ChatResponse`。其中 `chitchat` 仍会调用 LLM 生成闲聊回复，`off_topic` 和 `list` 不调用 retrieval 或 OpenAI。
- [x] 3.3 保留 QA 查询的现有“先检索、再回答”行为。
- [ ] 3.4 增加 chat 测试，覆盖澄清/闲聊 bypass、`rag_query` 检索，以及关闭配置后的回退行为。当前测试覆盖 QA handler 和 router 相关路径，但未覆盖关闭配置后的回退行为。

## 4. Search CLI 集成

- [ ] 4.1 在意图识别开启时，让 `search` 先分类输入，再做 embedding 配置校验和 manifest 加载。
- [ ] 4.2 对非 RAG 的 search 输入打印本地说明并成功退出。
- [ ] 4.3 保留 `rag_query` 的现有 search 输出和校验路径。
- [ ] 4.4 增加 CLI 测试，覆盖 `/help` bypass、正常 search 行为，以及关闭配置后的回退行为。当前 `search` CLI 仍直接执行检索，未集成意图识别。

## 5. 验证

- [x] 5.1 运行 `python -m pytest -q`。
- [x] 5.2 运行 `python -m compileall -q src tests`。
- [x] 5.3 运行 `mooomoocatrag --help`，确认 CLI 入口仍可加载。
