## 1. 配置与模型

- [x] 1.1 在 `Settings` 中新增 `QDRANT_*`、`ELASTICSEARCH_*`、`HYBRID_*` 配置项。
- [x] 1.2 扩展 `IndexManifest`，记录 `keyword_store`、`retrieval_mode`、`qdrant_collection`、`elasticsearch_index`。
- [x] 1.3 更新 `.env.example`，给出本地 OrbStack / port-forward 场景可用的默认样例。

## 2. 存储抽象与实现

- [x] 2.1 抽象当前 `vector_store`，拆出清晰的 dense / keyword store 边界。
- [x] 2.2 新增 `QdrantVectorStore`，实现 collection 初始化、upsert、delete、query 和一致性检查。
- [x] 2.3 新增 `ElasticsearchKeywordStore`，实现 index 初始化、bulk upsert、delete、keyword query 和一致性检查。
- [x] 2.4 移除或废弃当前直接绑定 `Chroma` 的运行时路径。

## 3. ingest 改造

- [x] 3.1 让 `ingest` 在每篇文章处理时同时写入 Qdrant 和 Elasticsearch。
- [x] 3.2 处理双写失败场景，保证失败时不更新 manifest。
- [x] 3.3 改造删除同步，同时删除 Qdrant point 和 ES document。
- [x] 3.4 为 `ingest --rebuild` 增加清空 Qdrant collection 和 ES index 的路径。

## 4. Hybrid 检索

- [x] 4.1 新增 hybrid retriever，整合 dense recall、keyword recall 和 RRF 融合。
- [x] 4.2 保留 manifest/content_hash 过滤和 token budget 截断。
- [x] 4.3 让 `search` 输出召回来源与融合结果。
- [x] 4.4 让 `chat` 使用新的 hybrid retriever 构造上下文。

## 5. K8s / OrbStack 依赖部署

- [x] 5.1 新增 `k8s/orbstack/` 目录结构，至少覆盖 namespace、Qdrant、Elasticsearch/ECK。
- [x] 5.2 新增启动、停止、port-forward 脚本。
- [x] 5.3 补充本地部署和凭据获取文档。

## 6. 测试

- [x] 6.1 更新存储层单元测试，覆盖 Qdrant / ES 一致性和错误路径。
- [x] 6.2 更新检索层测试，覆盖 dense-only、keyword-only、hybrid fusion 和 manifest 过滤。
- [x] 6.3 更新 CLI 测试，覆盖新配置和输出行为。
- [x] 6.4 增加最小 smoke test，验证依赖就绪时 `ingest/search/chat` 可以跑通。

## 7. 文档与验证

- [x] 7.1 更新 README 文档入口和配置说明。
- [x] 7.2 补充 `docs/` 下的架构与部署说明。
- [x] 7.3 运行 `./scripts/verify.sh`。
- [ ] 7.4 使用本地 OrbStack 做一次依赖启动与连接验证。
