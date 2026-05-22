# 文档治理与归档整理设计

## 背景

当前仓库同时存在 `openspec/changes/`、`docs/`、`docs/superpowers/` 和 `README.md` 的文档入口。它们各自有价值，但职责边界不够直观，容易出现以下问题：

- `README.md` 需要承载项目入口，但不适合堆放所有历史文档链接。
- `docs/` 下既有长期专题文档，也有历史计划、面试材料和流程规则。
- `docs/superpowers/` 记录了 Superpowers 设计与计划，但它不是 OpenSpec 的当前任务状态源。
- OpenSpec `tasks.md` 可能和实际代码进度不一致，导致 `openspec list` 给出过时状态。
- `docs/progress.md` 能记录状态变化，但不应成为唯一事实源。

本次整理选择“整理 + 归档/合并重复文档”方案，不强删历史文档，而是建立清晰入口、标注文档角色，并修正已知的任务状态漂移。

## 目标

- 新增统一的 `docs/README.md` 文档地图。
- 将现有文档按角色分类，降低查找成本。
- 明确 `openspec/changes/`、`docs/`、`docs/superpowers/`、`README.md` 的边界。
- 修正文档治理流程，让后续改动有明确的更新触发条件。
- 核对并更新已经明显过时的 OpenSpec `tasks.md` 状态。
- 保留历史资料，不做大规模删除。

## 非目标

- 不归档 OpenSpec change 到 `openspec/specs/`，因为仍存在未完成或待验收事项。
- 不删除历史计划、历史 Agent 分工、面试材料。
- 不把 Superpowers 文档改造成 OpenSpec 文档。
- 不处理主工作区中用户已有的未跟踪 refactor 文档，除非用户另行确认。
- 不伪造 OrbStack live 验收结果；没有真实运行就保持未完成状态。

## 文档分层

### 顶层 README

`README.md` 只保留项目简介、当前状态、安装运行方式，以及指向 `docs/README.md` 的文档入口。

它不承担完整文档索引，避免后续链接越堆越多。

### `docs/README.md`

新增为长期文档地图，按文档角色分区：

- 当前状态与变更日志
- 流程与治理规则
- 架构与设计
- 部署与运维
- 历史基线
- 学习与面试材料
- Superpowers 设计与计划归档
- OpenSpec 当前变更

每个条目说明用途、维护状态和过时触发条件。

### `docs/progress.md`

继续作为项目状态日志和阶段状态记录，但增加说明：它是状态摘要，不是唯一事实源。代码、测试、OpenSpec task 和长期文档需要一起核对。

### `openspec/changes/`

继续作为需求级改动源头。`proposal.md`、`design.md`、`spec.md`、`tasks.md` 的状态必须和实现同步。

当前重点核对：

- `add-intent-recognition`：代码和测试已经存在，`tasks.md` 仍显示未完成，需要按真实代码状态回填。
- `add-qdrant-es-hybrid-retrieval`：大部分完成，但 OrbStack live 验证仍未完成，保留未完成状态。

### `docs/superpowers/`

定位为“设计与实施计划归档”。它可以解释某次执行计划的来龙去脉，但不能替代 OpenSpec `tasks.md` 的当前状态。

## 过时治理规则

长期文档至少应满足以下一项：

- 在文档地图中标明维护状态。
- 在文档正文中标明历史定位。
- 在流程文档中定义更新触发条件。

后续出现以下情况时必须同步文档：

- CLI 命令、配置项、环境变量或部署方式变化：更新 `README.md` 和相关专题文档。
- 需求级能力完成或范围变化：更新对应 OpenSpec `tasks.md`，必要时更新 `proposal.md` / `design.md`。
- 项目阶段或验收状态变化：更新 `docs/progress.md`。
- 新增长期文档：更新 `docs/README.md`。

## 实施计划

1. 新增 `docs/README.md`，建立统一文档地图。
2. 收敛 `README.md` 的文档入口，指向文档地图。
3. 更新 `docs/change-documentation-workflow.md`，补充文档地图和过时治理规则。
4. 更新 `docs/progress.md`，记录本次治理，并标明状态日志定位。
5. 核对 intent 相关代码和测试后，更新 `openspec/changes/add-intent-recognition/tasks.md`。
6. 保持 `add-qdrant-es-hybrid-retrieval` 的 OrbStack live 验证未完成状态。
7. 运行 `./scripts/verify.sh` 和 OpenSpec strict validate。
8. 提交整理分支并合并回 `main`。

## 风险与约束

- 如果只按文件名归档，可能误判某些文档的当前价值；因此本次以“标注角色”为主，不强删。
- OpenSpec task 状态必须基于代码和测试核对，不根据记忆或标题推断。
- 主工作区已有未跟踪文档不属于本次工作范围，避免误提交用户 WIP。
- 文档整理属于治理性改动，验证重点是仓库验证命令、OpenSpec strict validate 和 git diff 清洁度。

## 自检

- 本设计没有 `TBD` / `TODO` 占位。
- 本设计选择的是第二档方案：整理、归档、合并重复入口，不强删历史文档。
- 实施范围覆盖入口、流程、状态日志和已知 OpenSpec task 漂移。
- OrbStack live 验证明确不伪装完成。
