## 为什么

当前项目的检索运行时仍然是本地 `Chroma + index_manifest.json` 单路 dense retrieval。这个形态适合 MVP，但有三个明显限制：

- 只有向量召回，没有关键词检索，遇到专有名词、缩写、标题词、短语词时召回不稳定。
- 向量存储依赖本地进程内目录，不适合作为后续生产环境依赖。
- 仓库没有 Kubernetes 依赖部署材料，无法用本地 OrbStack 或后续集群环境稳定复现检索基础设施。

用户已经明确下一阶段采用 `Qdrant + Elasticsearch`，并要求这些依赖通过 Kubernetes 部署。因此这次版本迭代需要把检索基础设施从本地 MVP 形态升级为“向量检索 + 关键词检索 + 混合召回 + K8s 依赖部署”的可演进架构。

## 变更内容

- 将运行时向量存储从本地 `Chroma` 迁移为 `Qdrant`。
- 新增 `Elasticsearch` 关键词索引，用于 BM25 / analyzer 驱动的关键词检索。
- 将当前单路检索改为 hybrid retrieval：`Qdrant dense recall + Elasticsearch keyword recall + RRF 融合`。
- 为 OrbStack 本地 Kubernetes 增加 repo-local 依赖部署方案，至少覆盖 `Qdrant`、`ECK/Elasticsearch` 和相关脚本/说明。
- 扩展配置、索引一致性校验、测试和文档，使 CLI 在保持 `ingest/search/chat` 入口不变的前提下接入新检索底座。

## 能力范围

### 新增能力

- `hybrid-retrieval-runtime`：支持 Qdrant + Elasticsearch 双路召回和 RRF 融合。
- `k8s-dependency-deployment`：支持在本地 OrbStack Kubernetes 中部署 Qdrant 和 Elasticsearch 依赖。

### 修改能力

- `ingest`：从“只写本地 Chroma”改为“写 Qdrant + 写 Elasticsearch + 更新 manifest”。
- `search` / `chat`：从“单路向量召回”改为“dense + keyword 融合召回”。
- `config`：新增 Qdrant、Elasticsearch、hybrid retrieval 参数。

## 不在本次范围

- 不在本次把应用本体改造成 Web 服务或容器化部署；第一阶段保留本地 CLI，先让依赖进入 K8s。
- 不在本次实现 rerank、query rewrite、parent-child retrieval、多 tenant 隔离或 ACL。
- 不在本次引入分布式 ingest 调度、后台任务系统或集群内文件同步。
- 不在本次追求生产级高可用参数模板；本次先交付“本地 OrbStack 可跑通 + 后续可扩展”的 repo 基线。

## 影响范围

- 影响代码：`src/mooomoocatrag/config.py`、`src/mooomoocatrag/models.py`、`src/mooomoocatrag/rag/`、`src/mooomoocatrag/ingest/`、`src/mooomoocatrag/cli.py`。
- 影响测试：`tests/test_vector_store.py`、`tests/test_retriever.py`、`tests/test_cli.py`，并新增 Qdrant / Elasticsearch 相关测试。
- 影响配置：新增 `QDRANT_*`、`ELASTICSEARCH_*`、`HYBRID_*` 配置项。
- 影响文档：新增检索架构设计文档、K8s 依赖部署文档，并更新 README 文档入口。
- 影响依赖：移除 `chromadb`，新增 `qdrant-client` 与 `elasticsearch` Python 客户端。
