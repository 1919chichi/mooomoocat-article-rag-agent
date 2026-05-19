## 背景

当前仓库的主链路是：

- `ingest` 扫描本地文章、切块、生成 embedding，并把向量写入 `Chroma`。
- `search` / `chat` 通过 query embedding 调用单路向量检索。
- `index_manifest.json` 负责记录文章级索引状态，并在查询阶段过滤失效 chunk。

这套链路已经满足 MVP，但它默认的设计前提是“单机、本地目录、单路 dense retrieval”。当目标切到“生产环境可用的向量数据库 + ES 关键词检索 + Kubernetes 依赖部署”时，需要明确收缩本次目标，避免同时做太多跨层改造。

## 目标 / 非目标

**目标：**

- 用 `Qdrant` 替代本地 `Chroma` 作为向量存储。
- 新增 `Elasticsearch` 关键词索引和查询路径。
- 在 `search` / `chat` 中实现基于 `RRF` 的 hybrid retrieval。
- 保持现有 CLI 命令入口 `ingest/search/chat` 不变。
- 提供本地 OrbStack K8s 依赖部署基线。
- 用尽量小的代码改造保留现有 `manifest` 增量索引契约。

**非目标：**

- 本次不把 CLI 改成 K8s 内运行的服务。
- 本次不移除本地 `index_manifest.json`；它仍然作为当前阶段的文章级索引状态源。
- 本次不实现 rerank、多向量、多路 query rewrite、在线热更新或高可用生产参数矩阵。
- 本次不引入独立元数据库；chunk 元数据以 `manifest + Elasticsearch 文档 + Qdrant payload` 组合维持。

## 关键假设

### 假设 1：应用本体先保留本地 CLI

用户当前明确要求的是“这些依赖使用 K8s 部署”，而不是“立刻把应用本体服务化”。因此本次默认：

- 本地 CLI 继续读取本地文章目录。
- Qdrant 和 Elasticsearch 通过 OrbStack K8s 暴露给本机 CLI 访问。
- 后续如果需要把应用本体也放进 K8s，再单独发起新变更。

### 假设 2：当前阶段保留本地 manifest

`index_manifest.json` 目前承担三件事：

- 记录文章级 `content_hash`。
- 记录每篇文章当前有效的 `chunk_ids`。
- 在检索时过滤失效 chunk。

如果现在同时移除 manifest、引入 Qdrant、引入 ES、再把应用本体 K8s 化，改动面过大。本次先保留 manifest，让“向量库替换 + 关键词检索 + K8s 依赖部署”成为唯一主线。

## 总体架构

```text
本地 Markdown/TXT 文章目录
        │
        ▼
scanner / parser / chunker
        │
        ▼
embedding generation
        │
        ├── write vectors + payload ───────► Qdrant
        │
        ├── write chunk documents ─────────► Elasticsearch
        │
        └── write article state ───────────► index_manifest.json

用户问题
   │
   ├── query embedding ───────────────────► Qdrant dense recall
   │
   ├── raw query ─────────────────────────► Elasticsearch keyword recall
   │
   └── fuse by RRF
              │
              ▼
      manifest/content_hash filtering
              │
              ▼
      token budget truncation
              │
              ▼
         RAG prompt / answer
```

## 设计决策

### 决策 1：先抽象 `VectorStore` / `KeywordStore`，再落具体实现

当前 `rag/vector_store.py` 直接绑定 `Chroma`。本次需要先把存储访问抽象为接口，再分别实现：

- `QdrantVectorStore`
- `ElasticsearchKeywordStore`

接口最少覆盖：

- `upsert_chunks`
- `delete_chunks`
- `query_dense`
- `query_keyword`
- `check_consistency`

这样做的原因是把“召回路径”从 `cli.py` 和 `retriever.py` 中拆出来，避免后续所有逻辑都变成 `if VECTOR_STORE == ...` / `if KEYWORD_STORE == ...`。

### 决策 2：第一阶段继续保留 manifest，作为文章级状态源

本次 `manifest` 不再记录“本地 Chroma 目录”语义，而是转为记录：

- `vector_store = qdrant`
- `keyword_store = elasticsearch`
- `retrieval_mode = hybrid_rrf`
- 当前 collection / index 的关键元信息

保留 manifest 的原因：

- 当前增量索引、删除同步和查询过滤都已经围绕它构建。
- 本地 CLI 仍然是单机写入，manifest 不会立刻成为并发瓶颈。
- 如果此时直接把 manifest 迁到 ES 或独立 DB，会让本次设计从“检索底座升级”扩张为“检索底座 + 元数据模型重构”。

代价是：如果未来应用本体进入多 Pod 或多 worker 场景，manifest 需要再升级为共享元数据源。

### 决策 3：Elasticsearch 只负责关键词召回和 chunk 文档索引

Elasticsearch 本次承担：

- `text` 字段的 BM25 关键词检索
- 文章标题、小标题、路径等结构化字段过滤/展示
- chunk 文档的可观测与排障入口

Elasticsearch 本次不承担：

- 向量 ANN 主召回
- 最终融合后的状态持久化

第一版中文 analyzer 默认从 `smartcn` 起步，后续如果发现召回问题，再升级为自定义 analyzer / 同义词配置。

### 决策 4：Qdrant 只负责 dense retrieval

Qdrant collection 至少包含：

- collection name：`mooomoocat_articles_v1`
- distance：`cosine`
- vector size：首次 ingest 自动探测并校验
- payload：
  - `chunk_id`
  - `article_id`
  - `chunk_index`
  - `title`
  - `nearest_heading`
  - `source_rel_path`
  - `content_hash`
  - `embedding_model`
  - `schema_version`

查询阶段只从 Qdrant 取 dense recall top-N，不把它扩展成全文搜索系统。

### 决策 5：用 RRF 做第一版融合

第一版 hybrid retrieval 使用 `Reciprocal Rank Fusion`：

- dense 结果来自 Qdrant
- keyword 结果来自 Elasticsearch
- 用统一 `chunk_id` 合并
- 用 `1 / (k + rank)` 计算融合分数

选择 RRF 的原因：

- 不需要先把 Qdrant 分数和 ES `_score` 强行映射到统一尺度。
- 对第一版比线性加权更稳妥，更容易测试。
- 后续如果加 rerank，也可以保留 RRF 作为召回层。

### 决策 6：OrbStack 本地 K8s 采用 repo-local 部署树

本次新增：

- `k8s/orbstack/eck/`：安装或引用 ECK operator 和 ES 集群清单
- `k8s/orbstack/qdrant/`：Qdrant 清单或 Helm values
- `bash/k8s/start-deps.sh`
- `bash/k8s/stop-deps.sh`
- `bash/k8s/port-forward.sh`

原因：

- 你已经明确本机使用 OrbStack。
- 当前仓库没有任何 K8s 资产，后续需要可重复的本地启动路径。
- repo-local 部署比单纯口头命令更适合长期维护。

## 配置设计

### 新增配置项

```env
VECTOR_STORE=qdrant
KEYWORD_STORE=elasticsearch
RETRIEVAL_MODE=hybrid_rrf

QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=mooomoocat_articles_v1

ELASTICSEARCH_URL=https://127.0.0.1:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=
ELASTICSEARCH_API_KEY=
ELASTICSEARCH_CA_CERT_PATH=
ELASTICSEARCH_INDEX=mooomoocat_article_chunks_v1
ELASTICSEARCH_ANALYZER=smartcn

HYBRID_DENSE_TOP_K=24
HYBRID_KEYWORD_TOP_K=24
HYBRID_FINAL_TOP_K=8
HYBRID_RRF_K=60
```

规则：

- `TOP_K` 逐步被 `HYBRID_FINAL_TOP_K` 取代，但在过渡期保持兼容。
- 如果同时配置 `ELASTICSEARCH_API_KEY` 与用户名密码，优先使用 API key。
- `QDRANT_COLLECTION` 和 `ELASTICSEARCH_INDEX` 视为一致性校验的一部分。

## 数据模型

### Qdrant point

- `id`: `chunk_id`
- `vector`: embedding 向量
- `payload`: chunk 结构化元数据

### Elasticsearch document

- `chunk_id`
- `article_id`
- `chunk_index`
- `title`
- `nearest_heading`
- `source_rel_path`
- `content_hash`
- `text`
- `updated_at`

其中 `text` 字段开启 analyzer，支持 BM25 关键词召回；`chunk_id` 唯一。

### Manifest 扩展

`IndexManifest` 需要补充或演进：

- `keyword_store`
- `retrieval_mode`
- `qdrant_collection`
- `elasticsearch_index`

同时现有 `vector_store` 字段从 `chroma` 改为 `qdrant`。

## ingest 改造

`ingest` 的文章级处理改为：

1. 扫描、解析、切块。
2. 生成 embedding。
3. 先 upsert Qdrant points。
4. 再 upsert Elasticsearch chunk documents。
5. 两边写入都成功后更新 manifest。
6. 对已删除文章，同时删除 Qdrant 和 ES 中对应 `chunk_id`。

如果只有一边写入成功：

- 本次直接报错，不更新 manifest。
- 提示用户重试或执行 `ingest --rebuild`。

这样虽然简单，但能保持 manifest 作为“已成功双写”的状态源。

## search / chat 改造

### Search

1. 生成 query embedding。
2. 调用 Qdrant 取 `HYBRID_DENSE_TOP_K`。
3. 调用 ES 取 `HYBRID_KEYWORD_TOP_K`。
4. 以 `chunk_id` 为键做 RRF 融合。
5. 按 manifest 过滤失效文章与 `content_hash` 不匹配项。
6. 按 token budget 和 `HYBRID_FINAL_TOP_K` 截断。
7. 输出结果，附带每条命中的召回来源，例如 `dense`、`keyword`、`hybrid`。

### Chat

与 Search 共享同一个 hybrid retriever，区别只在于最终输出进入 prompt。

## K8s / OrbStack 部署基线

本地 OrbStack 依赖部署至少要覆盖：

- namespace
- Qdrant StatefulSet / Service 或 Helm release
- ECK operator
- Elasticsearch 集群 CR
- 本地 port-forward 脚本
- 读取 ES 密码 / CA 的说明

文档中必须明确：

- 启动 OrbStack K8s 后再运行脚本。
- 如果 `kubectl` 当前 context 指向 `orbstack` 但 API Server 未启动，会得到 connection refused。
- 应用默认通过 `localhost` port-forward 访问 Qdrant 与 ES。

## 风险 / 取舍

- 保留 manifest 会让“完全生产化”再晚一步，但能显著缩小本次迁移面。
- Qdrant + ES 是双状态系统，ingest 需要处理双写失败；第一版通过“失败即不更新 manifest”保持保守一致性。
- ES 中文 analyzer 第一版先用 `smartcn`，召回质量未必最终最优，但足够作为起点。
- 本次先不把应用本体放进 K8s，因此“生产环境可用”主要指依赖底座，而不是整套运行时已经云原生。

## 迁移计划

1. 新增配置与数据模型。
2. 抽象并实现 Qdrant / ES store。
3. 改造 ingest 双写流程。
4. 改造 hybrid retriever 与 CLI。
5. 增加 K8s/OrbStack 部署资产。
6. 增加测试与文档。
7. 用真实文章和本机 OrbStack 做一次端到端验收。

## 回滚策略

- 代码层保留迁移分支前的 Chroma 实现，必要时可以在单独回滚提交中恢复。
- 如果 Qdrant / ES 迁移中断，本地 manifest 不更新，避免把部分成功写入当成有效索引。
- 真正切换到新架构前，应允许 `ingest --rebuild` 重新构建 Qdrant collection、ES index 和 manifest。
