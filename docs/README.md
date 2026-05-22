# 文档地图

> 最后核对：2026-05-22

本文件是仓库长期文档入口。`README.md` 只保留项目快速入口；查找设计、流程、历史资料和 OpenSpec 状态时，从这里开始。

## 维护规则

- 新增长期文档时，必须在本文登记。
- CLI、配置、部署方式或用户使用方式变化时，同步 `README.md` 和相关专题文档。
- 需求级能力完成、延期或范围变化时，同步对应 `openspec/changes/<change-id>/tasks.md`。
- 阶段状态或验收状态变化时，同步 `docs/progress.md`。
- `docs/superpowers/` 是设计与计划归档，不替代 OpenSpec 的当前任务状态。

## 当前状态

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [项目进度控制](progress.md) | 阶段状态和变更日志 | 持续维护 | 功能完成、验收状态或阻塞项变化 |

## 流程与治理规则

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [改动需求文档沉淀流程](change-documentation-workflow.md) | 文档与 OpenSpec 协作规则 | 持续维护 | 文档目录分工、交付流程或验证规则变化 |

## 架构与设计

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [Qdrant + Elasticsearch 混合检索改造设计](qdrant-es-hybrid-retrieval-design.md) | Hybrid retrieval 长期设计说明 | 随架构变化维护 | 检索存储、融合策略或部署方式变化 |

## 部署与运维

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [OrbStack 本地依赖部署说明](orbstack-local-deps.md) | Qdrant/Elasticsearch 本地依赖操作手册 | 持续维护 | K8s 清单、脚本、凭据读取或端口变化 |

## 历史基线

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [MVP 历史需求与任务拆分](mooomoocat-article-rag-agent-plan.md) | 项目早期计划和历史基线 | 历史资料 | 不作为当前实现状态来源 |
| [历史 Agent 分工](agent-roles.md) | 初始多 agent 分工记录 | 历史资料 | 不作为当前执行流程来源 |

## 学习与面试材料

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [RAG Agent 面试问题清单](rag-agent-interview-questions.md) | 学习和面试复盘材料 | 按需维护 | 面试准备范围或项目亮点变化 |

## Superpowers 设计与计划归档

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [意图识别设计方案](superpowers/specs/2026-05-22-intent-recognition-design.md) | Superpowers 设计归档 | 历史资料 | 不作为 OpenSpec 当前状态来源 |
| [Intent Recognition Implementation Plan](superpowers/plans/2026-05-22-intent-recognition.md) | Superpowers 实施计划归档 | 历史资料 | 不作为 OpenSpec 当前状态来源 |
| [文档治理与归档整理设计](superpowers/specs/2026-05-22-docs-consolidation-design.md) | 本次文档治理设计 | 本次完成后归档 | 文档治理规则再次调整 |
| [Documentation Consolidation Implementation Plan](superpowers/plans/2026-05-22-docs-consolidation.md) | 本次文档治理实施计划 | 本次完成后归档 | 文档治理规则再次调整 |

## OpenSpec 当前变更

| Change | 状态 | 说明 |
|---|---|---|
| `add-intent-recognition` | 部分实现，任务状态以 `tasks.md` 为准 | Chat/handler 主体和测试已存在；总开关与 search 集成仍未完成 |
| `add-qdrant-es-hybrid-retrieval` | 大部分完成，OrbStack live 验证未完成 | 保留真实依赖验收未完成状态，不伪装完成 |

## 判断真实状态的方法

不要只看单个文档判断项目状态。优先按下面顺序交叉核对：

1. 代码和测试：`src/`、`tests/`、`pyproject.toml`。
2. OpenSpec 状态：`openspec/changes/<change-id>/tasks.md` 和 `openspec list`。
3. 长期说明：`docs/README.md` 中登记的专题文档。
4. 状态摘要：`docs/progress.md`。
