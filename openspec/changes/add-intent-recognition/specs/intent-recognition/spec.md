## ADDED Requirements

### Requirement: 识别用户输入意图

系统 SHALL 在意图识别开启时，先把每次用户输入分类为一个且仅一个意图，再决定是否运行 RAG retrieval。

支持的意图必须包括：

- `rag_query`：输入是文章知识库问题，需要使用 RAG 流程。
- `clarification_needed`：输入过于模糊或依赖上下文，无法可靠检索。
- `chitchat`：输入是问候、感谢或纯礼貌交流。
- `control_command`：输入是已识别的命令式内容。
- `empty_or_invalid`：输入去除空白后为空，或不是可用查询。

#### Scenario: 文章问题被识别为 RAG 查询

- **WHEN** 用户输入为 `猫笔刀怎么理解长期主义？`
- **THEN** 系统将输入分类为 `rag_query`

#### Scenario: 空输入被识别为无效输入

- **WHEN** 用户输入只包含空白字符
- **THEN** 系统将输入分类为 `empty_or_invalid`

#### Scenario: 问候语被识别为闲聊

- **WHEN** 用户输入为 `你好`
- **THEN** 系统将输入分类为 `chitchat`

#### Scenario: 模糊追问需要澄清

- **WHEN** 用户输入为 `这个呢`
- **THEN** 系统将输入分类为 `clarification_needed`

#### Scenario: Slash command 被识别为控制命令

- **WHEN** 用户输入为 `/help`
- **THEN** 系统将输入分类为 `control_command`

### Requirement: 非 RAG 意图绕过 RAG

系统 SHALL 保证 `clarification_needed`、`chitchat`、`control_command`、`empty_or_invalid` 这些意图不会调用 embedding、vector search 或 chat completion 服务。

#### Scenario: Chat 对澄清场景绕过检索

- **WHEN** chat 收到被分类为 `clarification_needed` 的输入
- **THEN** 返回本地澄清提示
- **THEN** 返回空引用列表
- **THEN** 不调用 retrieval

#### Scenario: Chat 对闲聊场景绕过检索

- **WHEN** chat 收到被分类为 `chitchat` 的输入
- **THEN** 返回本地回复，并引导用户提出文章相关问题
- **THEN** 返回空引用列表
- **THEN** 不调用 retrieval

#### Scenario: Search 对命令输入绕过检索

- **WHEN** 执行 `mooomoocatrag search /help`
- **THEN** 命令打印本地说明
- **THEN** 不要求索引已经可用
- **THEN** 不调用 retrieval

### Requirement: 保留 RAG 查询的既有行为

系统 SHALL 保留被分类为 `rag_query` 的输入的现有强制检索行为。

#### Scenario: Chat 中的 RAG 查询仍然先检索

- **WHEN** chat 收到被分类为 `rag_query` 的输入
- **THEN** 在构造 RAG prompt 前先调用 retrieval
- **THEN** 只有 retrieval 返回可用结果时才调用 chat completion 服务

#### Scenario: Search 中的 RAG 查询返回检索片段

- **WHEN** 执行 `mooomoocatrag search "猫笔刀"`，且输入被分类为 `rag_query`
- **THEN** 命令校验 embedding 配置
- **THEN** 命令加载并校验 manifest
- **THEN** 命令按现有输出格式打印检索片段

### Requirement: 意图识别可配置

系统 SHALL 允许通过配置关闭意图识别。

#### Scenario: 关闭意图识别后恢复当前 chat 行为

- **WHEN** `ENABLE_INTENT_RECOGNITION` 为 false
- **AND** chat 收到非空输入
- **THEN** chat 将该输入当作 RAG 查询
- **THEN** chat 使用原始输入调用 retrieval

#### Scenario: 关闭意图识别后恢复当前 search 行为

- **WHEN** `ENABLE_INTENT_RECOGNITION` 为 false
- **AND** 执行 `mooomoocatrag search /help`
- **THEN** 命令将 `/help` 当作搜索 query
- **THEN** 命令走现有 search 校验和 retrieval 路径

### Requirement: 确定性离线分类

系统 SHALL 在不调用外部模型 API、不新增运行时依赖的情况下完成意图分类。

#### Scenario: 无 API 凭证时分类器仍可运行

- **WHEN** 使用 `你好` 调用分类器
- **THEN** 分类器返回意图决策，且不读取 embedding 或 LLM API 凭证

#### Scenario: 分类器输出稳定

- **WHEN** 使用同一个归一化输入多次调用分类器
- **THEN** 每次返回相同的意图和本地回复
