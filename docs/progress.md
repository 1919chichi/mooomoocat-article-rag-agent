# 项目进度控制

> 本文件由团队 lead 维护，记录各阶段完成状态和阻塞项。
> 最后更新：2026-05-08

---

## 总体状态：未开始

---

## 阶段 1：项目脚手架与配置

**状态**：⬜ 未开始
**负责 agent**：infra-agent
**前置依赖**：无

| 任务 | 状态 | 备注 |
|---|---|---|
| 创建 Python 项目结构（src/tests/docs 目录） | ⬜ | |
| 配置 pyproject.toml（依赖、requires-python>=3.10） | ⬜ | |
| 实现 config.py（pydantic-settings，所有环境变量 + 代码默认值） | ⬜ | |
| 创建 .env.example（只列核心配置和可选覆盖项） | ⬜ | |
| 实现 cli.py（typer 入口，ingest/search/chat 命令骨架） | ⬜ | |
| 实现 models.py（ArticleMeta / ChunkMeta / IndexManifest 数据类） | ⬜ | |
| 实现日志基础设施（LOG_LEVEL，API key 脱敏） | ⬜ | |
| 补充 .gitignore（data/ 等） | ⬜ | |

**完成标准**：`pip install -e .` 成功，`mooomoocatrag --help` 可用，配置加载正确

---

## 阶段 2：文章读取、解析和切块

**状态**：⬜ 未开始
**负责 agent**：ingest-agent
**前置依赖**：阶段 1 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 scanner.py（递归扫描 .md/.txt，计算 content_hash） | ⬜ | |
| 实现 parser.py（Markdown frontmatter/标题/正文，TXT 解析） | ⬜ | |
| 实现 chunker.py（标题感知+段落切分，nearest_heading，overlap 不跨标题边界） | ⬜ | |
| 实现 indexer.py（manifest 原子读写，增量索引，删除同步） | ⬜ | |
| 创建测试 fixtures（sample.md, sample.txt） | ⬜ | |
| 创建 conftest.py（fake embedding client，通用 fixture） | ⬜ | |
| 单元测试：test_parser.py | ⬜ | |
| 单元测试：test_chunker.py | ⬜ | |

**完成标准**：扫描/解析/切块/manifest 逻辑正确，单元测试通过，不依赖真实 API

---

## 阶段 3：向量化和索引

**状态**：⬜ 未开始
**负责 agent**：vector-agent
**前置依赖**：阶段 1 完成（可与阶段 2 并行）

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 embeddings.py（OpenAI-compatible API，base_url/api_key/model 可配） | ⬜ | |
| 实现 embedding 批处理和限流（batch=32，RPM=60，429/5xx 退避重试） | ⬜ | |
| 实现 vector_store.py（Chroma 持久化，collection 管理，chunk CRUD） | ⬜ | |
| 实现 embedding 模型一致性检查（模型/维度不一致提示 rebuild） | ⬜ | |
| 单元测试：test_embeddings.py | ⬜ | |
| 单元测试：test_vector_store.py | ⬜ | |

**完成标准**：embedding 批处理和限流正确，Chroma 读写正确，模型不一致时拒绝，测试不依赖真实 API

---

## 阶段 4：检索能力

**状态**：⬜ 未开始
**负责 agent**：rag-agent
**前置依赖**：阶段 2 + 阶段 3 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 retriever.py（top-k 查询，cosine→similarity 换算，overfetch） | ⬜ | |
| 实现相似度阈值过滤（SIMILARITY_THRESHOLD=0.5） | ⬜ | |
| 实现 manifest 有效 chunk 过滤（article_id + content_hash 匹配） | ⬜ | |
| 实现 prompt.py（RAG prompt 构造，引用编号，程序生成引用列表） | ⬜ | |
| 实现 LLM 调用封装（OpenAI-compatible Chat Completions） | ⬜ | |
| 实现 chat.py（强制检索，对话历史管理，无依据回答策略） | ⬜ | |
| 单元测试：test_retriever.py | ⬜ | |
| 单元测试：test_prompt.py | ⬜ | |
| 单元测试：test_chat.py | ⬜ | |

**完成标准**：检索流程正确，引用列表程序生成，无依据时明确说明，测试不依赖真实 API

---

## 阶段 5：集成与端到端

**状态**：⬜ 未开始
**负责 agent**：integration-agent
**前置依赖**：阶段 1-4 全部完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 串联 cli.py 中 ingest 命令（scanner→parser→chunker→embedding→vector_store→manifest） | ⬜ | |
| 实现 ingest --rebuild / --force | ⬜ | |
| 串联 cli.py 中 search 命令 | ⬜ | |
| 串联 cli.py 中 chat 命令（/exit /quit / Ctrl-D，会话统计） | ⬜ | |
| 错误处理完善（路径为空、目录不存在、无文章、API key 缺失） | ⬜ | |
| 端到端测试：test_ingest_e2e.py | ⬜ | |
| 端到端测试：test_search_e2e.py | ⬜ | |
| 端到端测试：test_chat_e2e.py | ⬜ | |
| 编写 README.md（从配置到运行的完整步骤） | ⬜ | |

**完成标准**：所有 CLI 命令可用，端到端测试通过，README 完整

---

## 阶段 6：验收

**状态**：⬜ 未开始
**负责 agent**：integration-agent + lead
**前置依赖**：阶段 5 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 构造手工评测问题（至少 10 个） | ⬜ | |
| 用真实文章跑通 ingest/search/chat | ⬜ | |
| 调整 chunk 参数和 SIMILARITY_THRESHOLD | ⬜ | |
| 确认 MVP 验收标准全部满足 | ⬜ | |
| 整理第二阶段优化项 | ⬜ | |

---

## 阻塞项

| 编号 | 描述 | 影响阶段 | 状态 | 备注 |
|---|---|---|---|---|
| B1 | ARTICLE_SOURCE_DIR 待填写 | 阶段 6 验收 | ⬜ | MVP 开发可用 fixture 文章 |
| B2 | EMBEDDING_MODEL / base_url / api_key 待填写 | 阶段 3+ | ⬜ | 开发阶段用 fake embedding client |
| B3 | LLM_MODEL / base_url / api_key 待填写 | 阶段 4+ | ⬜ | 开发阶段用 mock |

---

## 变更日志

| 日期 | 变更 |
|---|---|
| 2026-05-08 | 初始化进度文件 |
