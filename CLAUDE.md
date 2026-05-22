# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言

- 回复时使用中文。
- 新增或修改仓库文档时，默认使用中文。
- 技术标识符、代码符号、命令、配置项、文件路径可以保留英文。

## 常用命令

```bash
# 安装（含开发依赖）
python -m pip install -e ".[dev]"

# 验证（测试 + 编译检查 + CLI smoke test）
./scripts/verify.sh
# 或
make verify

# 运行全部测试
python -m pytest -q

# 运行单个测试文件
python -m pytest tests/test_retriever.py -q

# 运行单个测试函数
python -m pytest tests/test_retriever.py::test_retrieve_returns_empty_on_no_results -q
```

## 提交工作流

每次实际修改文件后：

1. 运行 `./scripts/verify.sh` 验证通过
2. `git status --short` 确认只暂存本次任务相关文件
3. 自动创建 git commit（Conventional Commits 格式：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`）
4. 默认不 push；只有用户明确要求时才 push
5. 验证失败则不提交，先说明失败原因

## 项目规约

@rules/python-best-practices.md

## 架构

### 包结构

```
src/mooomoocatrag/
├── cli.py          # Typer CLI：ingest / search / chat 三个子命令
├── config.py       # pydantic-settings Settings + get_settings() 单例
├── models.py       # 纯数据类：ArticleMeta, ChunkMeta, ParsedArticle, IndexManifest, RetrievalResult, ChatResponse
├── utils.py
├── ingest/         # 写入链路
│   ├── scanner.py  # 扫描文章目录，生成 ArticleMeta 列表
│   ├── parser.py   # 解析 .md / .txt，提取标题和正文
│   ├── chunker.py  # 标题感知切块，生成 ChunkMeta 列表
│   └── indexer.py  # manifest CRUD（增量索引、删除同步）
└── rag/            # 读取链路
    ├── embeddings.py   # OpenAI-compatible Embedding API，支持批量 + 速率限制
    ├── vector_store.py # Qdrant (dense) + Elasticsearch (keyword) 的读写适配层
    ├── retriever.py    # 混合检索 + RRF 融合 + token 预算截断
    ├── prompt.py       # RAG 提示词模板和常量
    ├── chat.py         # chat_turn：意图路由 → 分发到对应 handler
    └── intent/
        ├── router.py   # IntentRouter：调用 LLM 识别意图
        ├── types.py    # IntentType 枚举（CHITCHAT / OFF_TOPIC / LIST / SUMMARIZE / QA）
        └── handlers/   # 每种意图对应一个 handler 文件
```

### 核心数据流

**Ingest（写入）**：
`scan_articles` → `parse_article` → `chunk_article` → `embed_texts` → `upsert_dense_chunks` (Qdrant) + `upsert_keyword_chunks` (ES) → `save_manifest`

**Chat / Search（读取）**：
用户输入 → `IntentRouter.classify` → handler 分发 → `retrieve`（Qdrant dense + ES keyword → RRF 融合 → token 预算过滤）→ LLM 生成回答

### 关键设计约定

- **配置单例**：业务代码只用 `get_settings()`，禁止直接实例化 `Settings()`（见 `rules/python-best-practices.md`）。
- **manifest**：`data/index_manifest.json` 是索引状态的真相来源，记录每篇文章的 `content_hash`、`chunk_ids`、`embedding_model` 等，用于增量更新和删除同步。检索时会过滤 manifest 中 `deleted=True` 或 `content_hash` 不匹配的残留 chunk。
- **混合检索**：默认 `RETRIEVAL_MODE=hybrid_rrf`，Qdrant 负责语义向量检索，Elasticsearch 负责关键词检索，通过 RRF（Reciprocal Rank Fusion）融合后按 token 预算截断。
- **意图路由**：`chat_turn` 先通过 `IntentRouter` 识别意图，再路由到 `handle_chitchat` / `handle_off_topic` / `handle_list` / `handle_summarize` / `handle_qa`，只有 QA 类意图才强制走 RAG 检索。

### 外部依赖

| 依赖 | 用途 | 本地运行方式 |
|---|---|---|
| Qdrant | 向量检索 | OrbStack K8s（见 `docs/orbstack-local-deps.md`） |
| Elasticsearch | 关键词检索 | OrbStack K8s（ECK 部署） |
| OpenAI-compatible API | Embedding + LLM + 意图识别 | `.env` 配置 |

本地依赖启动：`bash/k8s/start-deps.sh`，停止：`bash/k8s/stop-deps.sh`，端口转发：`bash/k8s/port-forward.sh`。

### 测试约定

测试不依赖真实 API，通过 `conftest.py` 中的 `fake_settings`、`FakeEmbeddingClient` 等 fixture 隔离外部依赖。`test_hybrid_smoke.py` 是集成 smoke test，验证混合检索路径的整体串联逻辑。
