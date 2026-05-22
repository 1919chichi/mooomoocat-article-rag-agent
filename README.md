# mooomoocat-article-rag-agent

猫笔刀文章 RAG Agent。从本地 Markdown / TXT 文章目录构建知识库，CLI 对话时先检索相关文章片段，再结合检索结果用 LLM 回答。

---

## 目录

- [架构概览](#架构概览)
- [环境依赖](#环境依赖)
- [安装](#安装)
- [配置](#配置)
- [本地依赖启动（OrbStack K8s）](#本地依赖启动orbstack-k8s)
- [使用](#使用)
- [测试](#测试)
- [数据文件](#数据文件)

---

## 架构概览

### 包结构

```
src/mooomoocatrag/
├── cli.py          # Typer CLI：ingest / search / chat 三个子命令
├── config.py       # pydantic-settings Settings + get_settings() 单例
├── models.py       # 纯数据类：ArticleMeta, ChunkMeta, ParsedArticle, IndexManifest, RetrievalResult, ChatResponse
├── utils.py        # 共享工具：token 估算、重试、格式化
├── ingest/         # 写入链路
│   ├── scanner.py  # 扫描文章目录，生成 ArticleMeta 列表
│   ├── parser.py   # 解析 .md / .txt，提取标题和正文
│   ├── chunker.py  # 标题感知切块，生成 ChunkMeta 列表
│   └── indexer.py  # manifest CRUD（增量索引、删除同步）
└── rag/            # 读取链路
    ├── embeddings.py   # OpenAI-compatible Embedding API，批量 + 速率限制
    ├── vector_store.py # Qdrant (dense) + Elasticsearch (keyword) 读写适配
    ├── retriever.py    # 混合检索 + RRF 融合 + token 预算截断
    ├── prompt.py       # RAG 提示词模板和固定回复常量
    ├── chat.py         # chat_turn：意图路由 → 分发到对应 handler
    └── intent/
        ├── router.py          # IntentRouter：调用 LLM 识别意图
        ├── types.py           # IntentType 枚举
        └── handlers/          # 每种意图对应一个 handler
            ├── chitchat.py
            ├── off_topic.py
            ├── list.py
            ├── summarize.py
            └── qa.py
```

### 核心数据流

**Ingest（写入）**

```
scan_articles → parse_article → chunk_article
  → embed_texts
  → upsert_dense_chunks (Qdrant)
  → upsert_keyword_chunks (Elasticsearch)
  → save_manifest
```

**Chat / Search（读取）**

```
用户输入
  → IntentRouter.classify (LLM 识别意图)
  → handler 分发
      CHITCHAT / OFF_TOPIC → 直接回复，不检索
      LIST / SUMMARIZE / QA → retrieve
          Qdrant dense + ES keyword → RRF 融合 → token 预算过滤
          → LLM 生成回答
```

### 意图类型

| 意图 | 说明 |
|---|---|
| `CHITCHAT` | 闲聊，直接用 LLM 回复 |
| `OFF_TOPIC` | 超出文章库范围，拒绝回答 |
| `LIST` | 列举文章库中的内容 |
| `SUMMARIZE` | 摘要某篇或某类文章 |
| `QA` | 基于文章库的问答，强制走 RAG 检索 |

### 关键设计约定

- **配置单例**：业务代码只用 `get_settings()`，禁止直接实例化 `Settings()`。
- **manifest**：`data/index_manifest.json` 是索引状态的真相来源，记录每篇文章的 `content_hash`、`chunk_ids`、`embedding_model` 等，用于增量更新和删除同步。
- **混合检索**：默认 `RETRIEVAL_MODE=hybrid_rrf`，Qdrant 负责语义向量检索，Elasticsearch 负责关键词检索，通过 RRF（Reciprocal Rank Fusion）融合后按 token 预算截断。

---

## 环境依赖

### Python

- Python `>= 3.10`

### 外部服务

| 服务 | 用途 | 默认端口 |
|---|---|---|
| Qdrant | 向量语义检索 | `6333` (REST), `6334` (gRPC) |
| Elasticsearch | 关键词检索 | `9200` |
| OpenAI-compatible Embedding API | 文本向量化 | 配置指定 |
| OpenAI-compatible Chat API | LLM 对话 + 意图识别 | 配置指定 |

本地通过 OrbStack Kubernetes 运行 Qdrant 和 Elasticsearch，见[本地依赖启动](#本地依赖启动orbstack-k8s)。

---

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

验证 CLI：

```bash
mooomoocatrag --help
```

---

## 配置

复制配置模板：

```bash
cp .env.example .env
```

编辑 `.env`，字段说明：

### 必填

| 变量 | 说明 |
|---|---|
| `ARTICLE_SOURCE_DIR` | 文章源目录的绝对路径，支持 `.md` 和 `.txt` |
| `OPENAI_COMPAT_BASE_URL` | OpenAI-compatible API Base URL（LLM + Embedding 默认共用） |
| `OPENAI_COMPAT_API_KEY` | API Key |
| `EMBEDDING_MODEL` | Embedding 模型名称或推理接入点 ID |
| `LLM_MODEL` | Chat 模型名称 |

### 检索服务

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant REST 地址 |
| `QDRANT_API_KEY` | 空 | Qdrant API Key（本地可留空） |
| `QDRANT_COLLECTION` | `mooomoocat_articles_v1` | Qdrant collection 名称 |
| `ELASTICSEARCH_URL` | `https://127.0.0.1:9200` | Elasticsearch 地址 |
| `ELASTICSEARCH_USERNAME` | `elastic` | ES 用户名 |
| `ELASTICSEARCH_PASSWORD` | 空 | ES 密码（从 ECK secret 读取） |
| `ELASTICSEARCH_API_KEY` | 空 | ES API Key（与 username/password 二选一） |
| `ELASTICSEARCH_CA_CERT_PATH` | 空 | ES HTTPS CA 证书路径（ECK 部署时必填） |
| `ELASTICSEARCH_INDEX` | `mooomoocat_article_chunks_v1` | ES 索引名称 |
| `ELASTICSEARCH_ANALYZER` | `smartcn` | ES 分词器（中文推荐 smartcn） |

### 检索参数

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RETRIEVAL_MODE` | `hybrid_rrf` | 检索模式：`hybrid_rrf` / `dense` / `keyword` |
| `TOP_K` | `8` | 最终返回的检索结果数 |
| `SIMILARITY_THRESHOLD` | `0.3` | 向量相似度最低阈值 |
| `RAG_CONTEXT_TOKEN_BUDGET` | `6000` | RAG 上下文 token 预算 |
| `HYBRID_DENSE_TOP_K` | `24` | 混合检索时 Qdrant 候选数 |
| `HYBRID_KEYWORD_TOP_K` | `24` | 混合检索时 ES 候选数 |
| `HYBRID_FINAL_TOP_K` | `8` | RRF 融合后最终返回数 |
| `HYBRID_RRF_K` | `60` | RRF 公式中的 k 参数 |

### Embedding 独立配置（可选，当 Embedding 和 LLM 使用不同服务时）

| 变量 | 说明 |
|---|---|
| `EMBEDDING_PROVIDER` | `openai`（默认）或 `volcengine` |
| `EMBEDDING_BASE_URL` | Embedding API Base URL，覆盖 `OPENAI_COMPAT_BASE_URL` |
| `EMBEDDING_API_KEY` | Embedding API Key，覆盖 `OPENAI_COMPAT_API_KEY` |
| `LLM_BASE_URL` | LLM API Base URL，覆盖 `OPENAI_COMPAT_BASE_URL` |
| `LLM_API_KEY` | LLM API Key，覆盖 `OPENAI_COMPAT_API_KEY` |

### 其他参数

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_DIR` | `data` | 本地数据目录（存放 manifest） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `CHUNK_TARGET_MIN_CHARS` | `600` | 切块最小字符数 |
| `CHUNK_TARGET_MAX_CHARS` | `1000` | 切块最大字符数 |
| `CHUNK_OVERLAP` | `100` | 切块重叠字符数 |
| `CHAT_HISTORY_TURNS` | `4` | 对话保留的历史轮次 |
| `MAX_OUTPUT_TOKENS` | `2048` | LLM 单次输出 token 上限 |
| `INTENT_LLM_MODEL` | 空（使用 `LLM_MODEL`） | 意图识别专用模型，留空则复用 LLM_MODEL |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.6` | 意图置信度阈值 |

`.env` 不应提交到仓库，仓库只保留 `.env.example`。

---

## 本地依赖启动（OrbStack K8s）

本地通过 OrbStack Kubernetes 运行 Qdrant 和 Elasticsearch，脚本位于 `bash/k8s/`。

### 前置条件

- OrbStack 已安装，Kubernetes 已开启
- `kubectl` 已安装，当前 context 是 `orbstack`

验证：

```bash
kubectl config current-context   # 应输出 orbstack
kubectl cluster-info             # 能正常返回 control plane 信息
```

如需切换：

```bash
kubectl config use-context orbstack
```

### 版本基线

| 组件 | 版本 |
|---|---|
| ECK operator | `3.4.0` |
| Elasticsearch | `9.2.3` |
| Qdrant | `v1.18.0` |
| namespace | `mooomoocat-rag` |

### 启动依赖

```bash
bash/k8s/start-deps.sh
```

脚本依次执行：校验 context → 校验 API Server → 安装 ECK operator → 应用 `k8s/orbstack/` 清单 → 等待服务就绪。

查看 Pod 状态：

```bash
kubectl get pods -n mooomoocat-rag
kubectl get elasticsearch -n mooomoocat-rag
```

### 开启端口转发

另开一个终端，保持运行：

```bash
bash/k8s/port-forward.sh
```

默认建立：

- `http://127.0.0.1:6333` → Qdrant REST / Dashboard
- `grpc://127.0.0.1:6334` → Qdrant gRPC
- `https://127.0.0.1:9200` → Elasticsearch HTTPS

单独转发：

```bash
bash/k8s/port-forward.sh qdrant
bash/k8s/port-forward.sh es
```

### 读取 Elasticsearch 凭据

ECK 自动创建 `elastic` 用户密码和 HTTPS CA 证书。

读取密码：

```bash
kubectl get secret mooomoocat-es-es-elastic-user \
  -n mooomoocat-rag \
  -o go-template='{{.data.elastic | base64decode}}'
echo
```

导出 CA 证书：

```bash
kubectl get secret mooomoocat-es-es-http-certs-public \
  -n mooomoocat-rag \
  -o go-template='{{index .data "tls.crt" | base64decode}}' > /tmp/mooomoocat-es-ca.crt
```

将以下内容填入 `.env`：

```env
ELASTICSEARCH_PASSWORD=<从 secret 读取的密码>
ELASTICSEARCH_CA_CERT_PATH=/tmp/mooomoocat-es-ca.crt
```

验证连通性：

```bash
curl --cacert /tmp/mooomoocat-es-ca.crt \
  -u elastic:"$(kubectl get secret mooomoocat-es-es-elastic-user -n mooomoocat-rag -o go-template='{{.data.elastic | base64decode}}')" \
  https://127.0.0.1:9200
```

### 停止依赖

```bash
bash/k8s/stop-deps.sh
```

删除 `mooomoocat-rag` namespace 内所有资源，保留 ECK operator。如需同时删除 operator：

```bash
REMOVE_ECK_OPERATOR=true bash/k8s/stop-deps.sh
```

### K8s 清单目录结构

```
k8s/orbstack/
  namespace.yaml
  kustomization.yaml
  qdrant/
    service.yaml
    statefulset.yaml
  eck/
    elasticsearch.yaml

bash/k8s/
  start-deps.sh
  stop-deps.sh
  port-forward.sh
```

---

## 使用

### 首次索引文章

```bash
mooomoocatrag ingest
```

扫描 `ARTICLE_SOURCE_DIR` 下的所有 `.md` 和 `.txt` 文件，解析、切块、向量化，写入 Qdrant 和 Elasticsearch，并更新本地 manifest。

后续运行只处理新增或修改的文件（基于 `content_hash` 增量判断）。

### 重建索引

更换 Embedding 模型、调整切块参数或需要清空旧索引时：

```bash
mooomoocatrag ingest --rebuild          # 交互确认后清空重建
mooomoocatrag ingest --rebuild --force  # 跳过确认直接重建
```

### 测试检索

```bash
mooomoocatrag search "你想问的问题"
```

输出每个结果的融合分数、来源（dense/keyword）、文章标题、文件路径、chunk 索引和小标题。

### 进入对话

```bash
mooomoocatrag chat
```

- 系统先识别意图，再决定是否检索文章库
- 输入 `/exit` 或 `/quit`，或按 `Ctrl-D` 退出
- 退出时显示提问次数和引用文章数

---

## 测试

```bash
python -m pytest -q
```

运行单个文件：

```bash
python -m pytest tests/test_retriever.py -q
```

运行单个函数：

```bash
python -m pytest tests/test_retriever.py::test_retrieve_returns_empty_on_no_results -q
```

验证脚本（测试 + 编译检查 + CLI smoke test）：

```bash
./scripts/verify.sh
# 或
make verify
```

测试通过 `conftest.py` 中的 `fake_settings`、`FakeEmbeddingClient` 等 fixture 隔离外部依赖，不依赖真实 API。`test_hybrid_smoke.py` 是集成 smoke test，验证混合检索整体串联逻辑。

---

## 数据文件

| 路径 | 说明 |
|---|---|
| `data/index_manifest.json` | 文章索引状态，记录每篇文章的 `content_hash`、`chunk_ids`、`embedding_model` 等 |
| `.env` | 本地配置（不提交） |
| `.env.example` | 配置模板（提交） |

Qdrant 和 Elasticsearch 数据存储在各自服务中，本地只保留 manifest 文件。
