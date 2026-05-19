## ADDED Requirements

### Requirement: 系统支持 Qdrant 作为向量存储

系统 SHALL 使用 `Qdrant` 作为运行时向量存储，并用 collection 元信息校验当前索引配置是否一致。

#### Scenario: 首次 ingest 初始化 Qdrant collection

- **WHEN** 用户在空索引状态下执行 `mooomoocatrag ingest`
- **THEN** 系统创建或校验目标 Qdrant collection
- **THEN** collection 使用当前配置的向量维度和距离度量

#### Scenario: 向量配置不一致时拒绝继续

- **WHEN** manifest 或远端 Qdrant collection 记录的 embedding 模型、向量维度或 collection 名称与当前配置不一致
- **THEN** 系统报错
- **THEN** 系统提示用户执行 `mooomoocatrag ingest --rebuild`

### Requirement: 系统支持 Elasticsearch 关键词索引

系统 SHALL 为每个 chunk 写入可检索的 Elasticsearch 文档，并允许通过关键词查询召回 chunk。

#### Scenario: ingest 写入 Elasticsearch chunk 文档

- **WHEN** 一篇文章被切成多个 chunks 并进入 ingest 写入阶段
- **THEN** 系统为每个 chunk 写入一条 Elasticsearch 文档
- **THEN** 文档至少包含 `chunk_id`、`article_id`、`source_rel_path`、`content_hash` 和 `text`

#### Scenario: search 执行关键词召回

- **WHEN** 用户执行 `mooomoocatrag search "某个标题关键词"`
- **THEN** 系统对 Elasticsearch 执行关键词查询
- **THEN** 系统返回候选 chunk 参与后续融合

### Requirement: 系统执行 Hybrid Retrieval

系统 SHALL 在 `search` 和 `chat` 中执行 `Qdrant dense recall + Elasticsearch keyword recall + RRF 融合`，而不是只运行单路 dense retrieval。

#### Scenario: Search 融合 dense 与 keyword 结果

- **WHEN** 用户执行 `mooomoocatrag search "长期主义"`
- **THEN** 系统先生成 query embedding
- **THEN** 系统调用 Qdrant dense recall
- **THEN** 系统调用 Elasticsearch keyword recall
- **THEN** 系统使用 RRF 生成最终候选列表

#### Scenario: Chat 仍然在回答前先检索

- **WHEN** 用户在 `chat` 中提出文章问题
- **THEN** 系统在构造 RAG prompt 前执行 hybrid retrieval
- **THEN** 只有存在有效候选 chunk 时才调用 LLM

### Requirement: 融合结果保持 manifest 有效性过滤

系统 SHALL 在 dense / keyword 融合之后，继续使用 manifest 过滤失效文章和 `content_hash` 不匹配的 chunk。

#### Scenario: 已删除文章残留 chunk 不会被返回

- **WHEN** Qdrant 或 Elasticsearch 中残留了某个已删除文章的 chunk
- **AND** manifest 中已经不存在该 `article_id`
- **THEN** 系统不会把该 chunk 返回给 `search` 或 `chat`

#### Scenario: 内容 hash 不匹配的 chunk 被过滤

- **WHEN** 检索候选中的 `content_hash` 与 manifest 记录不一致
- **THEN** 系统丢弃该候选 chunk

### Requirement: ingest 对 Qdrant 与 Elasticsearch 采用保守双写

系统 SHALL 在同一篇文章的 Qdrant 与 Elasticsearch 写入都成功后，才更新 manifest。

#### Scenario: 双写都成功才更新 manifest

- **WHEN** 一篇文章的所有 chunk 已成功写入 Qdrant 和 Elasticsearch
- **THEN** 系统更新该文章在 manifest 中的 `content_hash`、`chunk_ids` 和时间戳

#### Scenario: 只有一边写入成功时不更新 manifest

- **WHEN** Qdrant 或 Elasticsearch 任意一边写入失败
- **THEN** 系统报错并中断本篇文章处理
- **THEN** 系统不更新该文章的 manifest 记录

### Requirement: 仓库提供 OrbStack K8s 依赖部署材料

系统 SHALL 提供 repo-local 的 Kubernetes 依赖部署材料，用于在本地 OrbStack 中启动 Qdrant 和 Elasticsearch。

#### Scenario: 仓库包含本地依赖部署目录

- **WHEN** 开发者检查仓库部署资产
- **THEN** 仓库包含 `k8s/orbstack/` 相关目录或等价结构
- **THEN** 该结构覆盖 Qdrant 与 Elasticsearch 依赖

#### Scenario: 仓库包含本地启动脚本

- **WHEN** 开发者准备在 OrbStack 中启动依赖
- **THEN** 仓库提供启动、停止或 port-forward 脚本
- **THEN** 文档说明如何访问本地暴露端口和获取凭据
