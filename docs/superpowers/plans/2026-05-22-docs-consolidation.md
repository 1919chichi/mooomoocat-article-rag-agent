# Documentation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立统一文档地图，整理现有 docs/OpenSpec/Superpowers 文档边界，并修正已知 OpenSpec task 状态漂移。

**Architecture:** `README.md` 保持项目入口，`docs/README.md` 成为长期文档地图，`docs/change-documentation-workflow.md` 定义后续治理规则，`docs/progress.md` 记录状态摘要，OpenSpec `tasks.md` 反映真实实现进度。

**Tech Stack:** Markdown, OpenSpec, Git worktree, `./scripts/verify.sh`, `openspec validate --strict`。

---

## File Map

- Create: `docs/README.md`，统一文档地图。
- Create: `docs/superpowers/plans/2026-05-22-docs-consolidation.md`，本实施计划。
- Modify: `README.md`，收敛文档入口到 `docs/README.md`。
- Modify: `docs/change-documentation-workflow.md`，补充文档地图、维护状态和过时触发规则。
- Modify: `docs/progress.md`，记录本次治理并标明状态日志定位。
- Modify: `openspec/changes/add-intent-recognition/tasks.md`，按真实代码和测试状态回填完成项。
- Read-only: `openspec/changes/add-qdrant-es-hybrid-retrieval/tasks.md`，保留 OrbStack live 验证未完成状态。

## Task 1: 新增统一文档地图

**Files:**
- Create: `docs/README.md`

- [ ] **Step 1: 编写 `docs/README.md`**

新增文档地图，使用以下结构：

```markdown
# 文档地图

> 最后核对：2026-05-22

本文件是仓库长期文档入口。`README.md` 只保留项目快速入口；查找设计、流程、历史资料和 OpenSpec 状态时，从这里开始。

## 维护规则

- 新增长期文档时，必须在本文登记。
- CLI、配置、部署方式或用户使用方式变化时，同步 `README.md` 和相关专题文档。
- 需求级能力完成、延期或范围变化时，同步对应 `openspec/changes/<change-id>/tasks.md`。
- 阶段状态或验收状态变化时，同步 `docs/progress.md`。

## 当前状态

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [项目进度控制](progress.md) | 阶段状态和变更日志 | 持续维护 | 功能完成、验收状态或阻塞项变化 |

## 流程与治理规则

| 文档 | 定位 | 维护状态 | 过时触发条件 |
|---|---|---|---|
| [改动需求文档沉淀流程](change-documentation-workflow.md) | 文档与 OpenSpec 协作规则 | 持续维护 | 文档目录分工或交付流程变化 |

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
| [文档治理与归档整理设计](superpowers/specs/2026-05-22-docs-consolidation-design.md) | 本次文档治理设计 | 随本次整理完成归档 | 文档治理规则再次调整 |
| [Documentation Consolidation Implementation Plan](superpowers/plans/2026-05-22-docs-consolidation.md) | 本次文档治理实施计划 | 随本次整理完成归档 | 文档治理规则再次调整 |

## OpenSpec 当前变更

| Change | 状态 | 说明 |
|---|---|---|
| `add-intent-recognition` | 部分实现，任务状态需以 `tasks.md` 为准 | Chat/handler 主体和测试已存在；总开关与 search 集成仍未完成 |
| `add-qdrant-es-hybrid-retrieval` | 大部分完成，OrbStack live 验证未完成 | 不伪造真实依赖验收结果 |
```

- [ ] **Step 2: 检查链接路径**

Run: `python - <<'PY'\nfrom pathlib import Path\nfor line in Path('docs/README.md').read_text().splitlines():\n    if '](' in line:\n        print(line)\nPY`

Expected: 输出的相对链接都指向 `docs/` 下已存在文件。

## Task 2: 收敛顶层 README 文档入口

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 替换 README 的文档区**

将 `## 文档` 下的多组链接改成：

```markdown
## 文档

完整文档入口见：

- [文档地图](docs/README.md)

常用入口：

- [项目进度控制](docs/progress.md)
- [改动需求文档沉淀流程](docs/change-documentation-workflow.md)
- [OrbStack 本地依赖部署说明](docs/orbstack-local-deps.md)
```

- [ ] **Step 2: 确认 README 不再重复维护完整文档索引**

Run: `rg -n "MVP 历史需求|历史 Agent|RAG Agent 面试" README.md`

Expected: 无输出。

## Task 3: 更新文档治理流程

**Files:**
- Modify: `docs/change-documentation-workflow.md`

- [ ] **Step 1: 更新核心原则**

在核心原则中加入：

```markdown
- 长期文档必须登记到 `docs/README.md`，并标明维护状态和过时触发条件。
- `docs/progress.md` 是状态摘要，不是唯一事实源；当前状态需要结合代码、测试、OpenSpec task 和专题文档判断。
- `docs/superpowers/` 是设计与实施计划归档，不替代 OpenSpec change 的任务状态。
```

- [ ] **Step 2: 更新目录分工表**

在目录分工表中增加 `docs/README.md` 和 `docs/superpowers/` 两行：

```markdown
| `docs/README.md` | 长期文档地图 | 文档分类、维护状态、过时触发条件、OpenSpec 当前变更入口 |
| `docs/superpowers/` | Superpowers 设计与计划归档 | 设计过程、实施计划、历史执行上下文 |
```

- [ ] **Step 3: 增加过时治理小节**

新增小节：

```markdown
### 6. 防止文档过时

每次改动结束前按下面规则核对：

- 新增长期文档：更新 `docs/README.md`。
- 用户使用方式变化：更新 `README.md`。
- 项目阶段、验收状态或阻塞项变化：更新 `docs/progress.md`。
- OpenSpec 需求完成、延期或范围变化：更新对应 `tasks.md`。
- Superpowers 设计或计划落地后：在 `docs/README.md` 标注为归档，不把它当作当前任务状态源。

如果某份文档只保留历史意义，在 `docs/README.md` 中标注为“历史资料”，不要继续把它当作当前实现依据。
```

## Task 4: 更新项目进度日志

**Files:**
- Modify: `docs/progress.md`

- [ ] **Step 1: 更新最后核对日期**

将最后更新日期改为：

```markdown
> 最后更新：2026-05-22
```

- [ ] **Step 2: 增加事实源说明**

在顶部说明后增加：

```markdown
> 本文件记录阶段状态摘要；判断当前真实状态时，还需要结合代码、测试、OpenSpec `tasks.md` 和 `docs/README.md`。
```

- [ ] **Step 3: 增加变更日志**

在变更日志顶部增加：

```markdown
| 2026-05-22 | 建立 `docs/README.md` 文档地图，明确 README、docs、OpenSpec、Superpowers 归档边界，并按真实代码状态回填意图识别 OpenSpec task |
```

## Task 5: 回填意图识别 OpenSpec task 状态

**Files:**
- Modify: `openspec/changes/add-intent-recognition/tasks.md`

- [ ] **Step 1: 核对代码和测试证据**

Run: `rg -n "Intent|intent|IntentRouter|handlers|test_intent" src/mooomoocatrag tests`

Expected: 输出包含 `src/mooomoocatrag/rag/intent/`、`src/mooomoocatrag/rag/chat.py`、`tests/test_intent_router.py` 和 `tests/fixtures/intent_cases.json`。

- [ ] **Step 2: 更新已实现任务**

将已实现任务标记为 `[x]`。保守处理：

- 1.1、1.2 标记完成。
- 1.3 如配置项实际存在则标记完成；如果配置项名称和原任务不一致，在条目后说明实际名称。
- 2.x 标记完成，但 2.1 的路径说明改为实际 package 结构 `src/mooomoocatrag/rag/intent/`。
- 3.x 标记完成。
- 4.x 如 search CLI 已集成则标记完成；若当前实现只覆盖 chat，则保持未完成并说明。
- 5.x 在验证通过后标记完成。

- [ ] **Step 3: 验证 OpenSpec 列表不再显示明显过时的 `0/18`**

Run: `openspec list`

Expected: `add-intent-recognition` 的完成数大于 0，并与 `tasks.md` 勾选状态一致。

## Task 6: 验证与提交

**Files:**
- Verify all modified files.

- [ ] **Step 1: 运行仓库验证**

Run: `./scripts/verify.sh`

Expected: 所有 pytest 通过，compileall、CLI help 和 diff check 通过。

- [ ] **Step 2: 运行 OpenSpec strict validate**

Run:

```bash
openspec validate add-intent-recognition --type change --strict --no-interactive
openspec validate add-qdrant-es-hybrid-retrieval --type change --strict --no-interactive
```

Expected: 两个 change 都通过 strict validate。

- [ ] **Step 3: 检查只暂存本次相关文件**

Run: `git status --short`

Expected: 只出现 README、docs、OpenSpec task 相关文件。

- [ ] **Step 4: 提交整理分支**

Run:

```bash
git add README.md docs/README.md docs/change-documentation-workflow.md docs/progress.md openspec/changes/add-intent-recognition/tasks.md docs/superpowers/plans/2026-05-22-docs-consolidation.md
git commit -m "docs: consolidate documentation map and task status"
```

Expected: 生成文档整理提交。

## Self-Review Checklist

- [ ] 计划覆盖设计文档中的所有实施项。
- [ ] 没有要求删除历史文档。
- [ ] 明确 `docs/superpowers/` 不替代 OpenSpec 状态。
- [ ] 明确 OrbStack live 验证不能伪装完成。
- [ ] 验证命令包含仓库验证和 OpenSpec strict validate。
