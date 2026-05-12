# 我的个人偏好

## 语言

- 回复时使用中文。
- 新增或修改仓库文档时，默认使用中文。
- OpenSpec 的 `proposal.md`、`design.md`、`spec.md`、`tasks.md` 默认使用中文撰写。
- 技术标识符、代码符号、命令、配置项、枚举值、文件路径，以及 OpenSpec 必需的结构关键字可以保留英文。

## 自动提交工作流

- 每次实际修改文件后，先运行仓库验证命令。
- 仓库验证入口优先使用 `scripts/verify.sh`，也可以运行 `make verify`。
- 如果本地环境缺少开发依赖，先运行 `python -m pip install -e '.[dev]'` 后再验证。
- 验证通过后，自动创建 git commit。
- 提交前必须执行 `git status --short`，只暂存本次任务相关文件。
- 不要提交用户已有的无关未提交改动、临时文件或其他任务的 WIP。
- 默认不 push；只有用户明确要求时才 push。
- 提交信息使用 Conventional Commits，例如 `feat: ...`、`fix: ...`、`docs: ...`、`chore: ...`。
- 如果验证失败，不要提交；先说明失败命令、失败原因和下一步处理。
