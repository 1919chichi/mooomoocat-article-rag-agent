## 背景

当前 CLI 从用户输入到检索是直接路径：

- `mooomoocatrag search <query>` 总是先校验 embedding 配置、加载 manifest，然后调用 `retrieve`。
- `mooomoocatrag chat` 在循环中直接处理 `/exit` 和 `/quit`，其他非空输入都会交给 `chat_turn`。
- `chat_turn` 总是在判断是否调用 LLM 前先调用 `retrieve`，这对文章问答场景是正确的，因为项目要求“先检索、再回答”。

这个流程已经能支撑 MVP，但它会把问候、命令式输入、模糊追问、无效输入都当成文章问题。意图识别层应该放在 retrieval 之前，先做显式路由决策，同时保留真实文章问题的现有 RAG 契约。

## 目标 / 非目标

**目标：**

- 在 retrieval 前增加确定性的用户输入意图分类。
- 将第一版意图集合控制在小而可测的范围：`rag_query`、`clarification_needed`、`chitchat`、`control_command`、`empty_or_invalid`。
- 只有 `rag_query` 进入现有 retrieval 和 LLM 流程。
- 对非 RAG 意图返回本地引导回复，不调用 embedding、vector store 或 LLM 服务。
- 提供配置开关，必要时可以关闭意图识别并恢复“所有输入都走 RAG”的当前行为。

**非目标：**

- MVP 不为了意图分类新增第二次 LLM 调用。
- 不实现 query rewrite、slot filling、多轮任务规划或工具调用。
- 不修改 ingest、chunking、Chroma 持久化、manifest schema 或引用格式。
- 不追求完整自然语言意图理解；本次只增加一个保守的显式路由层，用于识别明显情况。

## 设计决策

### 决策 1：第一版使用确定性的规则分类器

新增 `src/mooomoocatrag/rag/intent.py`，提供 `classify_intent(query: str, history: list[dict] | None = None) -> IntentDecision`。分类器先归一化空白字符，再按顺序应用规则：

1. 去除空白后为空 -> `empty_or_invalid`。
2. 识别 `/exit`、`/quit`、`/help` 等 slash command -> `control_command`。
3. 识别 `你好`、`hello`、`谢谢` 等问候或礼貌用语 -> `chitchat`。
4. 识别 `这个呢`、`继续`、`什么意思`、`详细说说` 等依赖上下文的模糊输入 -> `clarification_needed`。
5. 其他输入默认 -> `rag_query`。

备选方案是调用配置好的 chat model 来做意图分类。这个方案灵活性更高，但会在每个用户问题前增加延迟、成本、prompt 版本漂移和外部服务失败点。对本地 CLI MVP 来说，确定性分类器更合适，也更容易离线测试。

### 决策 2：路由结果用数据对象表达，而不是把控制流散落在 CLI 中

在 `models.py` 中新增 `IntentDecision` dataclass，字段包括：

- `intent: str`
- `normalized_query: str`
- `response: str`
- `reason: str`

`response` 用于非 RAG 场景的本地回复，例如要求用户补充问题或展示帮助信息。`normalized_query` 是 `rag_query` 场景下传给 retrieval 的 trimmed query。

备选方案是分类器只返回字符串枚举，然后让每个调用方自己决定输出内容。这样会让 `search`、`chat` 和未来入口重复实现响应逻辑。使用小型 decision object 可以让路由行为更明确，也更容易测试。

### 决策 3：同时在 CLI 和 chat 边界集成

`chat_turn` 在 `ENABLE_INTENT_RECOGNITION` 为 true 时先做分类。非 RAG 意图直接返回 `ChatResponse(answer=<本地回复>, citations=[], retrieved_count=0, intent=<intent>)`，不调用 `retrieve` 或 OpenAI。`rag_query` 保持当前行为：检索、处理无依据结果、构造 prompt、调用 LLM、生成引用。

`chat` 命令继续在循环中直接处理 `/exit` 和 `/quit`，因为这两个命令用于结束交互会话，而不是产生 assistant 回复。其他控制命令，例如 `/help`，可以交给 `chat_turn` 返回本地说明。

`search` 命令应该在 embedding 配置校验和 manifest 加载前先分类。非 RAG 输入打印本地回复并成功退出，不调用 `retrieve`。

备选方案是只在 `chat_turn` 内做分类。这样会让 `search` 保持旧行为，仍然会为命令式或无效输入浪费 embedding/config 工作。两个边界都集成可以让行为保持一致。

### 决策 4：增加默认开启的配置开关

在 `Settings` 中增加 `ENABLE_INTENT_RECOGNITION: bool = True`。当它为 false 时，`search` 和 `chat_turn` 对所有非空输入使用当前行为。

备选方案是让分类器始终开启。配置开关在真实文章/API 验收时有价值：如果规则过于激进，可以立即回退。

## 风险 / 取舍

- 规则分类可能误判短但有效的文章问题 -> 规则保持保守，模糊输入优先要求澄清，并允许通过 `ENABLE_INTENT_RECOGNITION=false` 关闭。
- 本地闲聊回复能力有限 -> 回复保持简短，并明确引导用户回到文章问题，而不是伪装成通用助手。
- `search` 和 `chat_turn` 的路由逻辑可能分叉 -> 两处复用同一个 `classify_intent` 函数和 `IntentDecision` 数据模型。
- 给 `ChatResponse` 增加 `intent` 字段会改变 dataclass 形状 -> 给字段设置默认值，保证现有测试和调用方构造 `ChatResponse` 时仍兼容。

## 迁移计划

1. 新增分类器、数据模型和默认开启的配置开关。
2. 集成 `chat_turn`，保留 `rag_query` 的现有行为和既有测试。
3. 集成 `search`，在非 RAG 输入场景下提前返回，避免配置校验和 manifest 加载。
4. 增加测试，覆盖分类规则、chat bypass、search bypass 和关闭配置后的回退行为。
5. 不需要数据迁移，因为本次不修改 Chroma 数据或 `index_manifest.json`。

回滚策略：设置 `ENABLE_INTENT_RECOGNITION=false` 即可恢复当前运行时行为；必要时可以回滚代码，不影响已索引数据。

## 待确认问题

- 第一版会把意图标签作为内部状态。如果后续需要可观测性，可以单独增加 debug 日志输出分类决策。
- query rewrite 不在本次范围内。如果追问质量成为下一个瓶颈，应作为独立变更提案处理。
