## 为什么

当前 `search` 和 `chat` 会把所有用户输入都当作知识库检索问题处理，无法区分退出、闲聊、无效输入、需要澄清的问题，或者真正需要 RAG 的文章问答。增加意图识别可以让 CLI 在进入 embedding 检索和 LLM 回答前做轻量路由，减少无意义检索，并为后续更复杂的 Agent 行为打下边界清晰的基础。

## 变更内容

- 新增用户输入意图识别能力，在 `search` 和 `chat` 的 RAG 处理前判断输入属于哪类意图。
- 支持最小可落地的意图集合：`rag_query`、`clarification_needed`、`chitchat`、`control_command`、`empty_or_invalid`。
- 对不应进入 RAG 的输入返回明确的本地处理结果，例如提示用户补充问题、输出可用命令说明，或跳过空输入。
- 保持现有“强制先检索、再回答”的约束：只有被识别为 `rag_query` 的输入才进入 retrieval 和 LLM 回答流程。
- 增加配置开关，允许在需要时关闭意图识别并回退到当前行为。
- 补充单元测试和 CLI 编排测试，覆盖每类意图的路由行为。

## 能力范围

### 新增能力

- `intent-recognition`：识别用户输入意图，并在进入 RAG 检索前给出可测试的路由决策。

### 修改能力

- 无。

## 影响范围

- 影响代码：`src/mooomoocatrag/cli.py`、`src/mooomoocatrag/rag/chat.py`、`src/mooomoocatrag/config.py`、`src/mooomoocatrag/models.py`，以及 `src/mooomoocatrag/rag/` 下新增的意图识别模块。
- 影响测试：新增意图识别单元测试，并更新 `tests/test_chat.py` 和 `tests/test_cli.py`。
- CLI 接口：命令签名保持兼容；`chat` 对非 RAG 输入可能输出本地引导回复。
- 依赖：MVP 不新增运行时依赖；第一版使用确定性的规则分类。
