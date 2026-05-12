# 改动需求文档沉淀流程

本文档规定本仓库后续每一次需求改动如何沉淀为可追溯文档。目标不是为每个小改动写长文，而是让需求背景、实现范围、测试结果和后续结论都有稳定入口。

## 核心原则

每次改动至少留下一个文档记录点：

- 需求级改动：先写 `openspec/changes/<change-id>/`，再实现。
- 架构或长期设计决策：补充 `docs/<topic>-design.md` 或 ADR 风格决策记录。
- 项目状态变化：更新 `docs/progress.md`。
- 用户使用方式变化：更新 `README.md`。

不要把所有内容都塞进 README。README 只保留项目入口、当前状态、运行方式和关键文档链接；过程、取舍和验收记录放到 `docs/` 或 `openspec/changes/`。

## 目录分工

| 位置 | 用途 | 适合记录 |
|---|---|---|
| `openspec/changes/<change-id>/proposal.md` | 改动前的需求说明 | 为什么改、改什么、不改什么、影响范围 |
| `openspec/changes/<change-id>/tasks.md` | 改动前的任务拆分 | 可勾选的实现、测试、验证步骤 |
| `openspec/changes/<change-id>/design.md` | 较复杂改动的设计说明 | 方案取舍、接口边界、风险、兼容性 |
| `docs/progress.md` | 项目状态与变更日志 | 阶段状态、阻塞项、完成记录 |
| `docs/<topic>.md` | 长期专题文档 | 缓存策略、意图识别、验收方案、操作手册 |
| `README.md` | 项目首页 | 文档入口、安装运行、最小可用说明 |

## 标准流程

### 1. 收到需求后先判断类型

按影响范围分三档：

| 类型 | 示例 | 文档要求 |
|---|---|---|
| 小修小补 | 改错别字、调整日志文案、补一条测试 | 更新 `docs/progress.md` 变更日志即可 |
| 需求级改动 | 增加意图识别、增加缓存、调整 CLI 行为 | 新建 `openspec/changes/<change-id>/` |
| 架构级改动 | 更换向量库、调整索引模型、引入新服务 | OpenSpec change + `docs/<topic>-design.md` |

如果不确定，按“需求级改动”处理。这个仓库更看重可追溯性，轻量 OpenSpec change 的成本可以接受。

### 2. 改动前创建 OpenSpec change

命名使用短横线：

```text
openspec/changes/add-intent-recognition/
openspec/changes/add-embedding-cache/
openspec/changes/improve-real-api-validation/
```

最少包含：

```text
proposal.md
tasks.md
```

复杂改动再增加：

```text
design.md
specs/<capability>/spec.md
```

`proposal.md` 建议包含：

```markdown
## 为什么

说明当前问题、触发背景、用户价值。

## 变更内容

- 具体会新增、修改或删除什么能力。

## 能力范围

### 新增能力

- ...

### 修改能力

- ...

## 不在本次范围

- 明确哪些看似相关但这次不做。

## 影响范围

- 影响代码
- 影响测试
- CLI / 配置 / 数据兼容性
- 依赖变化
```

`tasks.md` 必须可执行、可勾选：

```markdown
## 1. Implementation

- [ ] 1.1 ...
- [ ] 1.2 ...

## 2. Tests

- [ ] 2.1 ...

## 3. Documentation

- [ ] 3.1 Update docs/progress.md.
- [ ] 3.2 Update README.md if user-facing behavior changes.

## 4. Verification

- [ ] 4.1 Run python -m pytest -q.
- [ ] 4.2 Run python -m compileall -q src tests.
- [ ] 4.3 Run mooomoocatrag --help if CLI behavior changed.
```

### 3. 实现时同步任务状态

实现过程中不要只改代码。每完成一块，就同步更新对应 `tasks.md`：

```markdown
- [x] 1.1 Add settings field.
- [x] 1.2 Add unit tests.
- [ ] 1.3 Update CLI integration.
```

如果实现中发现原设计不合适，不要只在代码里绕过去，需要回写 `proposal.md` 或 `design.md`，说明实际采用的方案。

### 4. 完成后更新长期文档

改动完成后按影响范围更新：

- 更新 `docs/progress.md` 的最后更新时间、阶段状态和变更日志。
- 如果新增了稳定能力，补 `docs/<topic>.md`，写清楚使用方式、边界和验证方法。
- 如果用户使用命令、配置或环境变量发生变化，更新 `README.md`。
- 如果只是内部实现变化，不需要扩大 README，只在 `docs/progress.md` 和专题文档里记录。

### 5. 验证后再提交

常规验证命令：

```bash
python -m pytest -q
python -m compileall -q src tests
mooomoocatrag --help
git diff --check
```

文档-only 改动至少执行：

```bash
git diff --check
```

提交信息建议带上改动类型：

```text
docs: add change documentation workflow
feat: add intent recognition routing
fix: handle empty article directory
```

## 完成标准

一次需求改动只有同时满足下面条件，才算真正完成：

- OpenSpec change 记录了需求背景、范围和任务拆分。
- 代码和测试已实现并通过必要验证。
- `tasks.md` 勾选到真实完成状态。
- `docs/progress.md` 记录了项目状态变化。
- 用户可见行为变化已同步到 README 或专题文档。
- 最终提交里同时包含代码、测试和文档改动。

## 给 Codex 的固定指令

以后可以直接这样要求：

```text
这次改动按 docs/change-documentation-workflow.md 走：
先创建 OpenSpec change，改完代码和测试后同步 docs/progress.md，
如果影响用户使用再更新 README，最后给我验证结果。
```

如果只是文档或小修，可以说：

```text
这是小改动，不需要 OpenSpec change，只更新 docs/progress.md 和必要文档。
```
