# 项目进度控制

> 本文件由团队 lead 维护，记录各阶段完成状态和阻塞项。
> 最后更新：2026-05-12

---

## 总体状态：MVP 代码已打通，待真实文章/API 验收

已完成本地 CLI 主链路：`ingest -> Chroma/manifest -> search -> chat`。当前自动化测试覆盖模块逻辑和 CLI 编排，真实文章目录与真实 OpenAI-compatible API 仍需用户配置后手工验收。

---

## 阶段 1：项目脚手架与配置

**状态**：✅ 已完成
**负责 agent**：infra-agent
**前置依赖**：无

| 任务 | 状态 | 备注 |
|---|---|---|
| 创建 Python 项目结构（src/tests/docs 目录） | ✅ | `src/mooomoocatrag`、`tests`、`docs` 已存在 |
| 配置 pyproject.toml（依赖、requires-python>=3.10） | ✅ | 已配置 console script `mooomoocatrag` |
| 实现 config.py（pydantic-settings，所有环境变量 + 代码默认值） | ✅ | 支持 `.env` 和默认值 |
| 创建 .env.example（只列核心配置和可选覆盖项） | ✅ | 不含真实敏感值 |
| 实现 cli.py（typer 入口，ingest/search/chat 命令骨架） | ✅ | 三个业务命令已串联实现 |
| 实现 models.py（ArticleMeta / ChunkMeta / IndexManifest 数据类） | ✅ | 另含 ParsedArticle / RetrievalResult / ChatResponse |
| 实现日志基础设施（LOG_LEVEL，API key 脱敏） | ✅ | `setup_logging` 已实现 |
| 补充 .gitignore（data/ 等） | ✅ | 已排除 `.env`、`data/`、缓存和构建产物 |

**完成标准**：`pip install -e ".[dev]"` 成功，`mooomoocatrag --help` 可用，配置加载正确。

---

## 阶段 2：文章读取、解析和切块

**状态**：✅ 已完成
**负责 agent**：ingest-agent
**前置依赖**：阶段 1 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 scanner.py（递归扫描 .md/.txt，计算 content_hash） | ✅ | 跳过隐藏目录，使用 UTF-8 读取并报清晰错误 |
| 实现 parser.py（Markdown frontmatter/标题/正文，TXT 解析） | ✅ | 支持 `source_root` / `source_rel_path`，子目录引用不丢失 |
| 实现 chunker.py（标题感知+段落切分，nearest_heading，overlap 不跨标题边界） | ✅ | 长 section 拆分后保留 heading，overlap 不跨 heading |
| 实现 indexer.py（manifest 原子读写，增量索引，删除同步） | ✅ | helper + CLI 编排完成；manifest 使用原子写入 |
| 创建测试 fixtures（sample.md, sample.txt） | ✅ | 已存在 |
| 创建 conftest.py（fake embedding client，通用 fixture） | ✅ | 已存在 |
| 单元测试：test_parser.py | ✅ | 已覆盖 frontmatter、H1 fallback、相对路径等 |
| 单元测试：test_chunker.py | ✅ | 已覆盖 heading、长 section、overlap 边界等 |
| 单元测试：test_scanner.py / test_indexer.py | ✅ | 补充扫描与 manifest helper 覆盖 |

**完成标准**：扫描/解析/切块/manifest 逻辑正确，单元测试通过，不依赖真实 API。

---

## 阶段 3：向量化和索引

**状态**：✅ 已完成，真实 API 待验收
**负责 agent**：vector-agent
**前置依赖**：阶段 1 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 embeddings.py（OpenAI-compatible API，base_url/api_key/model 可配） | ✅ | 使用 `openai` SDK |
| 实现 embedding 批处理和限流（batch=32，RPM=60，429/5xx 退避重试） | ✅ | 有单测覆盖 |
| 实现 vector_store.py（Chroma 持久化，collection 管理，chunk CRUD） | ✅ | `add/delete/query` 已实现 |
| 实现 embedding 模型一致性检查（模型/维度不一致提示 rebuild） | ✅ | 检查模型、维度、向量库、距离度量、chunker 配置 |
| 单元测试：test_embeddings.py | ✅ | mock API，不依赖真实服务 |
| 单元测试：test_vector_store.py | ✅ | mock Chroma，覆盖一致性检查 |

**完成标准**：embedding 批处理和限流正确，Chroma 读写逻辑正确，模型/维度不一致时拒绝，测试不依赖真实 API。

---

## 阶段 4：检索能力

**状态**：✅ 已完成
**负责 agent**：rag-agent
**前置依赖**：阶段 2 + 阶段 3 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 实现 retriever.py（top-k 查询，cosine→similarity 换算，overfetch） | ✅ | overfetch 由 vector store 统一处理 |
| 实现相似度阈值过滤（SIMILARITY_THRESHOLD=0.5） | ✅ | 有单测覆盖 |
| 实现 manifest 有效 chunk 过滤（article_id + content_hash 匹配） | ✅ | 防止残留 chunk 返回 |
| 实现 prompt.py（RAG prompt 构造，引用编号，程序生成引用列表） | ✅ | 引用不暴露绝对路径 |
| 实现 LLM 调用封装（OpenAI-compatible Chat Completions） | ✅ | `chat_turn` 中封装 |
| 实现 chat.py（强制检索，对话历史管理，无依据回答策略） | ✅ | 每轮强制检索；预算不足时保留高相似 chunk |
| 单元测试：test_retriever.py | ✅ | 已覆盖排序、阈值、manifest 过滤、预算 |
| 单元测试：test_prompt.py | ✅ | 已覆盖 prompt 和引用 |
| 单元测试：test_chat.py | ✅ | 已覆盖历史裁剪、无依据回答、引用 |

**完成标准**：检索流程正确，引用列表程序生成，无依据时明确说明，测试不依赖真实 API。

---

## 阶段 5：集成与端到端

**状态**：🟨 集成已完成，端到端真实环境待补强
**负责 agent**：integration-agent
**前置依赖**：阶段 1-4 全部完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 串联 cli.py 中 ingest 命令（scanner→parser→chunker→embedding→vector_store→manifest） | ✅ | 已输出索引摘要 |
| 实现 ingest --rebuild / --force | ✅ | 支持清空 Chroma 与 manifest |
| 串联 cli.py 中 search 命令 | ✅ | 输出相似度、标题、相对路径、chunk、小标题、片段预览 |
| 串联 cli.py 中 chat 命令（/exit /quit / Ctrl-D，会话统计） | ✅ | 已输出答案、引用和会话统计 |
| 错误处理完善（路径为空、目录不存在、无文章、API key 缺失） | ✅ | CLI 启动前做配置检查 |
| 端到端测试：test_ingest_e2e.py | 🟨 | 当前 `tests/test_cli.py` 用 mock 覆盖 CLI 编排，真实 Chroma/API e2e 待补 |
| 端到端测试：test_search_e2e.py | 🟨 | 当前 `tests/test_cli.py` 覆盖输出格式 |
| 端到端测试：test_chat_e2e.py | 🟨 | 当前 `tests/test_cli.py` 覆盖交互流程 |
| 编写 README.md（从配置到运行的完整步骤） | ✅ | 已更新 |

**完成标准**：所有 CLI 命令可用，自动化测试通过；真实文章/API 端到端测试仍归阶段 6 验收。

---

## 阶段 6：验收

**状态**：⬜ 待开始
**负责 agent**：integration-agent + lead
**前置依赖**：阶段 5 完成

| 任务 | 状态 | 备注 |
|---|---|---|
| 构造手工评测问题（至少 10 个） | ⬜ | |
| 用真实文章跑通 ingest/search/chat | ⬜ | 依赖用户填写真实 `ARTICLE_SOURCE_DIR` 与 API 配置 |
| 调整 chunk 参数和 SIMILARITY_THRESHOLD | ⬜ | 依据真实召回效果调整 |
| 确认 MVP 验收标准全部满足 | ⬜ | |
| 整理第二阶段优化项 | ⬜ | |

---

## 阻塞项

| 编号 | 描述 | 影响阶段 | 状态 | 备注 |
|---|---|---|---|---|
| B1 | ARTICLE_SOURCE_DIR 待填写 | 阶段 6 验收 | ⬜ | MVP 开发可用 fixture 文章；真实验收需用户本机路径 |
| B2 | EMBEDDING_MODEL / base_url / api_key 待填写 | 阶段 6 验收 | ⬜ | 单元测试用 mock；真实 ingest/search 需真实配置 |
| B3 | LLM_MODEL / base_url / api_key 待填写 | 阶段 6 验收 | ⬜ | 单元测试用 mock；真实 chat 需真实配置 |

---

## 变更日志

| 日期 | 变更 |
|---|---|
| 2026-05-12 | 整理 docs 文档结构：规范化 RAG Agent 面试问题清单，补充历史规划和历史 Agent 分工定位，重组 README 文档入口 |
| 2026-05-12 | 新增改动需求文档沉淀流程，并在 README 增加文档入口 |
| 2026-05-08 | 打通 CLI ingest/search/chat 主链路，补齐 parser/indexer/retriever/vector_store/chat/chunker 缺口，新增 CLI/scanner/indexer 测试，更新 README |
| 2026-05-08 | 初始化进度文件 |
