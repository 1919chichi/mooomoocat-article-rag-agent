# Agent 角色定义与分工

> 本文档记录 MVP 初始开发阶段的历史 Agent 分工，用于理解当时的模块边界和协作方式。后续新需求的任务拆分以对应的 OpenSpec change 为准。

## 概述

本项目使用 Team Agent 模式开发，共 5 个 agent，按职责分工并行推进。
每个 agent 负责一个独立的代码领域，通过模块接口（Python 函数签名 / 数据类）协作。

---

## Agent 列表

### 1. infra-agent — 基础设施

**职责**：项目骨架、配置、CLI、日志、数据模型

**负责文件**：
- `pyproject.toml` — 依赖管理、项目元数据
- `.env.example` — 环境变量模板
- `src/mooomoocatrag/__init__.py`
- `src/mooomoocatrag/config.py` — pydantic-settings 配置加载，包含所有环境变量和代码默认值
- `src/mooomoocatrag/cli.py` — typer CLI 入口（ingest / search / chat 命令骨架）
- `src/mooomoocatrag/models.py` — Article / Chunk 数据类定义
- `.gitignore` — 补充 data/ 目录等忽略规则

**交付标准**：
- `pip install -e .` 能成功安装
- `mooomoocatrag --help` / `mooomoocatrag ingest --help` 能输出帮助
- `config.py` 能从 `.env` 加载所有配置项，缺省值正确
- `models.py` 定义 `ArticleMeta`、`ChunkMeta`、`IndexManifest` 数据类
- 日志不打印 API key（脱敏处理）

**依赖**：无（最先启动）

**产出接口（其他 agent 依赖）**：
- `config.py` 中的 `Settings` 类 — 所有 agent 读取配置的来源
- `models.py` 中的数据类 — 所有 agent 交换数据的契约
- `cli.py` 中的命令入口 — 后续 agent 在此挂载实际逻辑

---

### 2. ingest-agent — 文章摄取

**职责**：文件扫描、正文解析、切块、manifest 管理

**负责文件**：
- `src/mooomoocatrag/ingest/scanner.py` — 递归扫描 .md/.txt 文件，计算 content_hash
- `src/mooomoocatrag/ingest/parser.py` — Markdown frontmatter / 标题 / 正文提取，TXT 解析
- `src/mooomoocatrag/ingest/chunker.py` — 标题感知 + 段落切分，保留 nearest_heading / chunk_index
- `src/mooomoocatrag/ingest/indexer.py` — manifest 原子读写、增量索引逻辑、删除同步
- `tests/fixtures/sample.md` — 测试用 Markdown 样例
- `tests/fixtures/sample.txt` — 测试用 TXT 样例
- `tests/conftest.py` — fake embedding client 和通用 fixture
- `tests/test_parser.py`
- `tests/test_chunker.py`

**交付标准**：
- `scanner.py` 能递归扫描指定目录，跳过隐藏目录，返回文件列表 + content_hash
- `parser.py` 能正确提取标题（frontmatter > 一级标题 > 文件名）和清洗后正文
- `chunker.py` 能按标题结构切块，nearest_heading 正确，overlap 不跨标题边界
- `indexer.py` 能原子写入 manifest，增量跳过未变化文件，删除同步时 warning 不中断
- 单元测试覆盖标题提取、空文件、长文章、中文段落、hash 未变化跳过
- 所有测试使用 fixture 文章，不依赖真实 API

**依赖**：infra-agent（config.py、models.py）

**产出接口（其他 agent 依赖）**：
- `scanner.py` → `scan_articles(source_dir) -> list[ArticleMeta]`
- `parser.py` → `parse_article(file_path, file_type) -> ParsedArticle`
- `chunker.py` → `chunk_article(parsed_article, config) -> list[ChunkMeta]`
- `indexer.py` → `load_manifest(data_dir) -> IndexManifest`
- `indexer.py` → `save_manifest(manifest, data_dir) -> None`

---

### 3. vector-agent — 向量化与存储

**职责**：embedding 生成、Chroma 向量库操作、批处理与限流

**负责文件**：
- `src/mooomoocatrag/rag/embeddings.py` — OpenAI-compatible Embeddings API 封装
- `src/mooomoocatrag/rag/vector_store.py` — Chroma 持久化、collection 管理、chunk CRUD
- `tests/test_embeddings.py`
- `tests/test_vector_store.py`

**交付标准**：
- `embeddings.py` 支持 OpenAI-compatible API，可配置 base_url / api_key / model
- `embeddings.py` 实现批量请求（EMBEDDING_BATCH_SIZE=32）、RPM 限流、429/5xx 指数退避重试
- `vector_store.py` 能持久化 chunk 向量和元数据，collection 名称固定 `mooomoocat_articles`
- `vector_store.py` 支持写入 chunk、按 chunk_ids 删除、相似度查询
- `vector_store.py` 创建 collection 时写入 metadata（hnsw:space、schema_version、embedding_model、embedding_dimension）
- embedding 模型/维度与 manifest 不一致时提示 rebuild
- 单元测试覆盖 batch、限流重试、模型不一致、增量跳过；使用 fake embedding client

**依赖**：infra-agent（config.py、models.py）

**产出接口（其他 agent 依赖）**：
- `embeddings.py` → `embed_texts(texts, config) -> list[list[float]]`
- `vector_store.py` → `add_chunks(chunks_with_vectors, config) -> None`
- `vector_store.py` → `delete_chunks(chunk_ids, config) -> None`
- `vector_store.py` → `query_similar(query_vector, top_k, config) -> list[QueryResult]`

---

### 4. rag-agent — 检索与对话

**职责**：retriever、prompt 构造、LLM 调用、chat 流程

**负责文件**：
- `src/mooomoocatrag/rag/retriever.py` — 检索 top-k，阈值过滤，manifest 有效 chunk 过滤
- `src/mooomoocatrag/rag/prompt.py` — RAG prompt 构造，引用编号，程序生成引用列表
- `src/mooomoocatrag/rag/chat.py` — 强制检索对话流程，对话历史管理，无依据回答策略
- `tests/test_retriever.py`
- `tests/test_prompt.py`
- `tests/test_chat.py`

**交付标准**：
- `retriever.py` 输入问题返回 top-k chunk，统一 similarity 分数（0-1），不暴露 Chroma 原始 distance
- `retriever.py` 按 SIMILARITY_THRESHOLD 过滤，按 manifest 过滤有效 chunk
- `prompt.py` 构造包含检索片段和引用编号的 prompt，引用列表由程序生成
- `chat.py` 每次问题都先执行检索（代码层面强制，非提示词约束）
- `chat.py` 保留最近 CHAT_HISTORY_TURNS=4 轮，预算不足先裁剪历史
- `chat.py` 无足够检索结果时明确说"猫笔刀文章库中没有找到足够依据"
- 引用列表只使用相对路径，不暴露本机绝对路径
- 单元测试覆盖强制检索、历史裁剪、无依据回答、引用列表生成

**依赖**：infra-agent（config.py、models.py）、vector-agent（embeddings.py、vector_store.py）

**产出接口（其他 agent 依赖）**：
- `retriever.py` → `retrieve(query, config, manifest) -> list[RetrievalResult]`
- `chat.py` → `chat_turn(query, history, config, manifest) -> ChatResponse`

---

### 5. integration-agent — 集成与端到端

**职责**：CLI 命令实现串联、ingest 完整流程、search 命令、chat 命令、端到端测试、错误处理、README

**负责文件**：
- `src/mooomoocatrag/cli.py`（补充完善，串联各模块逻辑）
- `tests/test_ingest_e2e.py` — 端到端 ingest 测试
- `tests/test_search_e2e.py` — 端到端 search 测试
- `tests/test_chat_e2e.py` — 端到端 chat 测试
- `README.md` — 从配置到运行的完整步骤

**交付标准**：
- `mooomoocatrag ingest` 能完成扫描、切块、入库、删除同步、摘要输出
- `mooomoocatrag ingest --rebuild` 能清空重建，默认需确认，--force 跳过确认
- `mooomoocatrag search "问题"` 输出片段和来源
- `mooomoocatrag chat` 进入连续对话，/exit /quit / Ctrl-D 退出，退出时打印会话统计
- 路径为空、目录不存在、无文章、API key 缺失都有清晰报错
- 端到端测试用 fixture 文章验证 ingest/search/chat；不依赖真实 API
- README 有完整配置和运行步骤

**依赖**：所有其他 agent 完成后启动

---

## 并行策略

```
时间线 →

infra-agent  ████████
              │
ingest-agent          ██████████████
                      │
vector-agent          ██████████████
                      │          │
rag-agent                      ██████████████
                               │
integration-agent                      ██████████████
```

**第一批并行**（阶段 1 完成后）：
- ingest-agent 和 vector-agent 可同时启动

**第二批**（阶段 2+3 完成后）：
- rag-agent 启动（依赖 vector-agent 的接口）

**第三批**（所有功能完成后）：
- integration-agent 串联所有模块

## 协作规则

1. **接口先行**：每个 agent 先定义自己产出的函数签名和数据类，提交后再写实现
2. **不修改他人文件**：只修改自己负责的文件，如需改动他人接口，通过消息协调
3. **测试自给**：每个 agent 自己写自己模块的单元测试
4. **配置统一**：所有配置从 `config.py` 的 `Settings` 类读取，不自行解析 `.env`
5. **模型统一**：所有数据类使用 `models.py` 中的定义，不自行定义
