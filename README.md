# mooomoocat-article-rag-agent

猫笔刀文章 RAG Agent 项目。

第一版目标：从本地 Markdown / TXT 文章目录构建知识库，通过 CLI 对话时强制先检索相关文章，再结合检索结果回答。

## 当前状态

- 已实现本地 CLI：`ingest`、`search`、`chat`。
- 已实现文章扫描、Markdown/TXT 解析、标题感知切块、Chroma 向量库写入、manifest 增量索引、删除同步、检索过滤、RAG prompt 和对话流程。
- 已有离线测试覆盖主要模块和 CLI 编排，测试不依赖真实 OpenAI-compatible API。
- 真实文章目录和真实 API 配置仍需在本机 `.env` 中填写后做人工验收。

## 文档

- [需求与任务拆分](docs/mooomoocat-article-rag-agent-plan.md)
- [项目进度控制](docs/progress.md)
- [Agent 分工](docs/agent-roles.md)

## 环境要求

- Python `>=3.10`
- 本地可写数据目录，默认 `data/`
- OpenAI-compatible Embeddings API
- OpenAI-compatible Chat Completions API

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

验证 CLI 是否可用：

```bash
mooomoocatrag --help
```

## 配置

复制配置模板：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
ARTICLE_SOURCE_DIR=/path/to/articles
OPENAI_COMPAT_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_COMPAT_API_KEY=your-api-key
EMBEDDING_MODEL=your-embedding-model
LLM_MODEL=your-chat-model
```

如果 Embedding 和 LLM 使用不同服务，可以使用可选覆盖项：

```bash
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
LLM_BASE_URL=
LLM_API_KEY=
```

`.env` 不应提交到仓库；仓库只提交 `.env.example`。

## 使用

首次索引文章：

```bash
mooomoocatrag ingest
```

更换 embedding 模型、chunk 参数或需要清空旧索引时重建：

```bash
mooomoocatrag ingest --rebuild
mooomoocatrag ingest --rebuild --force
```

测试检索：

```bash
mooomoocatrag search "你想问的问题"
```

进入连续对话：

```bash
mooomoocatrag chat
```

在 chat 中输入 `/exit`、`/quit` 或按 `Ctrl-D` 退出。

## 测试

```bash
python -m pytest -q
```

当前测试使用 fixture、mock 和 fake 配置，不依赖真实 API。

## 数据文件

默认数据写入：

- `data/chroma/`：Chroma 向量库
- `data/index_manifest.json`：文章索引 manifest

这些运行时数据已被 `.gitignore` 排除。
