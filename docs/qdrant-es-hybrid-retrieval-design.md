# Qdrant + Elasticsearch 混合检索改造设计

## 1. 这次改什么

这次版本迭代不再继续沿用本地 `Chroma` 作为运行时向量库，而是把检索底座调整为：

- `Qdrant`：负责向量 ANN 检索
- `Elasticsearch`：负责关键词 / BM25 检索
- `RRF`：负责融合 dense 和 keyword 两路候选

同时，仓库会补齐 `k8s/orbstack` 依赖部署资产，让本地 OrbStack Kubernetes 可以把这两个依赖跑起来。

## 2. 为什么现在做这件事

当前仓库已经完成了本地 RAG MVP，主链路是 `ingest -> Chroma/manifest -> search -> chat`。这条链路的问题不在“不能跑”，而在于：

- 向量库仍然是本地目录形态，不适合后续生产依赖。
- 检索只有 dense，没有 keyword，专有词和标题词命中不稳。
- 没有 K8s 部署资产，后续无法把依赖稳定迁到 OrbStack / 集群环境。

所以这次改造的本质，不是“换个库名”，而是把项目从单机 MVP 的检索底座升级成可继续演进的 hybrid retrieval 架构。

## 3. 本次边界

本次默认边界是：

- 应用本体先保留本地 CLI。
- 文章源目录仍然来自本地文件系统。
- `Qdrant` 和 `Elasticsearch` 作为依赖通过 K8s 运行。
- `index_manifest.json` 暂时保留，继续承担文章级索引状态记录。

也就是说，这次先把“检索底座”和“依赖部署方式”升级掉，而不是一次性把整套应用服务化。

## 4. 架构变化

### 4.1 旧链路

```text
article files
  -> parser/chunker
  -> embeddings
  -> Chroma
  -> dense retrieval
  -> prompt
  -> answer
```

### 4.2 新链路

```text
article files
  -> parser/chunker
  -> embeddings
  -> Qdrant
  -> Elasticsearch
  -> index_manifest.json

user query
  -> query embedding -> Qdrant dense recall
  -> raw query       -> Elasticsearch keyword recall
  -> RRF fusion
  -> manifest/content_hash filter
  -> prompt
  -> answer
```

## 5. 为什么保留 manifest

这次一个容易误判的点是：既然都上 `Qdrant + ES` 了，为什么不顺手把 `manifest` 干掉。

原因是当前 manifest 不只是“本地缓存文件”，它还是当前项目的文章级真相源，负责：

- 记录 `content_hash`
- 跟踪每篇文章当前有效的 `chunk_ids`
- 在查询阶段过滤残留脏数据

如果现在同时做：

- Chroma -> Qdrant
- 新增 ES keyword index
- 干掉 manifest
- 重新设计文章元数据状态源

那这次改造会从“底座升级”膨胀成“检索底座 + 元数据模型重构”。这不是一个合适的第一步。

所以本次策略是：manifest 暂时保留，但语义升级为 `Qdrant + ES` 场景下的文章级状态文件。

## 6. 为什么是 Qdrant + ES，而不是 ES-only

这次已经做过方案判断，最终选择 `Qdrant + ES`，原因是：

- `Qdrant` 更适合专职做 dense retrieval。
- `Elasticsearch` 更适合承担 analyzer、BM25、中文关键词检索。
- 后续调优时，向量检索和关键词检索可以独立演进。

代价也很明确：状态系统从一个变成两个，ingest 需要双写一致性处理。

第一版接受这个代价，换取边界清晰。

## 7. ingest 要怎么改

每篇文章的 ingest 流程改为：

1. 解析文章并切块。
2. 生成每个 chunk 的 embedding。
3. upsert 到 `Qdrant`。
4. upsert 到 `Elasticsearch`。
5. 两边都成功后，更新 manifest。
6. 如果文章被删除，同时删 Qdrant point 和 ES document。

关键原则：

- 双写都成功，manifest 才前进。
- 任意一边失败，manifest 不更新。
- 不做复杂自动修复，出问题优先让用户重试或 `ingest --rebuild`。

## 8. search / chat 要怎么改

检索改为双路：

- dense 路：query embedding -> Qdrant
- keyword 路：raw query -> Elasticsearch

融合方式第一版使用 `RRF`，原因是简单、稳定，而且不要求 Qdrant 分数和 ES `_score` 先强行归一化。

融合后的结果仍然要保留当前项目已经验证过的两个约束：

- 必须过 manifest 有效性过滤
- 必须过 token budget 截断

这两个约束不能因为底座升级而丢掉。

## 9. 配置项会怎么变化

至少会新增这些配置：

```env
VECTOR_STORE=qdrant
KEYWORD_STORE=elasticsearch
RETRIEVAL_MODE=hybrid_rrf

QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=mooomoocat_articles_v1

ELASTICSEARCH_URL=https://127.0.0.1:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=
ELASTICSEARCH_INDEX=mooomoocat_article_chunks_v1
ELASTICSEARCH_ANALYZER=smartcn

HYBRID_DENSE_TOP_K=24
HYBRID_KEYWORD_TOP_K=24
HYBRID_FINAL_TOP_K=8
HYBRID_RRF_K=60
```

第一版默认走本地 `port-forward` 访问方式，方便 OrbStack K8s 中的依赖被本机 CLI 调用。

## 10. K8s / OrbStack 要补什么

仓库内会新增 repo-local 部署树，至少包括：

- `k8s/orbstack/qdrant/`
- `k8s/orbstack/eck/`
- `bash/k8s/start-deps.sh`
- `bash/k8s/stop-deps.sh`
- `bash/k8s/port-forward.sh`

文档里需要明确写出：

- OrbStack K8s 必须先启动
- `kubectl` context 指向 `orbstack` 但 API server 没起来时会报 connection refused
- ES 密码、CA、port-forward 的获取方式

## 11. 这次不做什么

这次不做：

- 应用本体容器化
- rerank
- query rewrite
- 多 tenant
- 后台调度
- 元数据共享数据库

这些都应该在这次底座升级稳定后，再拆下一轮变更。

## 12. 建议实施顺序

1. 新增配置和数据模型
2. 抽象 `VectorStore` / `KeywordStore`
3. 实现 `QdrantVectorStore`
4. 实现 `ElasticsearchKeywordStore`
5. 改造 ingest 双写
6. 改造 hybrid retriever
7. 增加 `k8s/orbstack` 部署资产
8. 补测试和 README
9. 用真实文章 + OrbStack 做一次 smoke test

## 13. review 时重点看什么

你 review 这版设计时，建议重点看 4 个点：

- 这次是否接受“应用本体先不进 K8s”
- 这次是否接受“manifest 先保留”
- ingest 的“双写都成功再更新 manifest”是否符合你的风险偏好
- `Qdrant + ES` 的边界是否清晰，没有重新耦成一个大杂烩
